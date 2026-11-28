"""One identify request, from scan to a saved job: the flow behind the ripper identify route."""

import asyncio
import logging
from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend import iso_prepare, job_events
from arm_backend.job_failure import fail_job, scan_failure_text
from arm_backend.disc_dedupe import find_previous_rips, find_reusable_job_for_disc
from arm_backend.metadata import MetadataDispatcher
from arm_backend.metadata.base import MetadataResult
from arm_backend.metadata.dispatcher import DISPATCH_TIMEOUT_SECONDS, Identification
from arm_backend.metadata.identity_payload import first_str
from arm_backend.metadata.match.explain import log_line
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_backend.identity.apply import apply_identity_result, suggest_identity, suggest_shortlist
from arm_backend.identity.episode_stage import is_tv_candidate
from arm_backend.identity.pipeline import resolve_job, run_disc_hints, source_name_of
from arm_backend.identity.proposals import put_source
from arm_backend.identity.sources.base import Source
from arm_backend.identity.sources.registry import auto_apply_for, enabled_hint_sources
from arm_backend.identity.sources.thediscdb import (
    SOURCE_ID as THEDISCDB,
    build_claims,
    external_imdb_id,
    release_identity,
    release_kind,
    release_result,
)
from arm_backend.identity.sources.thediscdb_snapshot import DiscMatch, SnapshotStore
from arm_backend.identity.stage_runner import EpisodeStageRunner
from arm_backend.review_tracks import persist_review_tracks
from arm_backend.ws import WSHub
from arm_common import (
    Config,
    DiscFingerprint,
    Drive,
    Job,
    JobStatus,
    MediaType,
    Session,
)
from arm_common.logging import with_log_context
from arm_common.enums import VIDEO_DISC_TYPES, DriveKind, PreviouslyRippedAction
from arm_common.models import Track
from arm_common.schemas import (
    ScanFailure,
    flag_is_set,
    with_flags,
    IdentifyRequest,
    ScanResult,
    IdentifyMatch,
)

logger = logging.getLogger("arm_backend.identify_flow")


# A miss stores at most this many dispatcher attempts (metadata_json.identify_attempts).
MAX_IDENTIFY_ATTEMPTS = 20

_T = TypeVar("_T")


class UnknownDriveError(Exception):
    """The request names no enrolled drive."""

    def __init__(self, drive_id: str) -> None:
        super().__init__(drive_id)
        self.drive_id = drive_id


def pause_refuses_new_jobs(cfg: Config | None) -> bool:
    """Whether the global pause turns a new job away. With the timed review gate on, a
    paused machine still scans + identifies + PARKS the disc for review (pause only
    suppresses auto-start at expiry); with it off, pause means reject outright.
    Shared by disc insertion, Start rip and ISO rips so the three never disagree."""
    return cfg is not None and bool(cfg.ripping_paused) and not cfg.hold_for_review


class RippingPausedError(Exception):
    """Ripping is paused and the review gate is off, so no new job is accepted."""


class DiscAlreadyRippedError(Exception):
    """on_previously_ripped=reject refused a disc that an earlier job already ripped."""

    def __init__(self, previous_job_id: str) -> None:
        super().__init__(previous_job_id)
        self.previous_job_id = previous_job_id


async def _record_duplicate_rejection(
    session: AsyncSession, hub: WSHub, drive: Drive, previous: Job, scan: ScanResult
) -> None:
    """on_previously_ripped=reject: create no job, record the refusal against
    the earlier rip (event + inbox) and leave a note on the drive. The caller
    raises the refusal once this is committed."""
    title = previous.title or scan.volume_label or "an untitled disc"
    when = f" on {previous.ripped_at.date().isoformat()}" if previous.ripped_at else ""
    drive.notice = f"Ejected a disc already ripped as {title}{when}."
    session.add(drive)
    await hub.emit(
        topic="ripper.events",
        event_type="rip.duplicate_rejected",
        payload={
            "drive_id": drive.id,
            "volume_label": scan.volume_label,
            "disc_type": scan.disc_type.value,
            "previous_job_id": previous.id,
        },
        job_id=previous.id,
        session=session,
    )
    await session.commit()
    logger.info("identify drive_id=%s: disc already ripped as %s; rejecting it", drive.id, previous.id)


class IdentifyFlow:
    """One identify request, from scan to a saved job: finds or creates the job, identifies the disc and holds it."""

    def __init__(
        self,
        *,
        req: IdentifyRequest,
        thediscdb_store: SnapshotStore | None,
        session: AsyncSession,
        dispatcher: MetadataDispatcher,
        hub: WSHub,
        stage_runner: EpisodeStageRunner | None,
    ) -> None:
        self.req = req
        self.thediscdb_store = thediscdb_store
        self.session = session
        self.dispatcher = dispatcher
        self.hub = hub
        self.stage_runner = stage_runner
        self.drive: Drive | None = None
        self.cfg: Config | None = None
        self.scan: ScanResult | None = None
        self.fps: list[tuple[str, str]] = []
        self.reuse_job: Job | None = None
        self.previous: Job | None = None
        self.job: Job | None = None
        self.already_identified = False
        self.prior_status: JobStatus | None = None
        self.hints: tuple[Source, ...] = ()
        self.thediscdb_match: DiscMatch | None = None
        self.iso_name: str | None = None
        self.result: MetadataResult | None = None
        # Why the weighted search decided as it did (None for a CD or a whole-dispatch timeout).
        self.match: IdentifyMatch | None = None
        self.timed_out = False
        self.attempts: list[dict[str, Any]] = []

    async def _load_drive(self) -> Drive:
        drive = (
            await self.session.execute(select(Drive).where(col(Drive.id) == self.req.drive_id))
        ).scalar_one_or_none()
        if drive is None:
            raise UnknownDriveError(self.req.drive_id)
        return drive

    def _mark_new_disc(self, drive: Drive) -> None:
        # An ISO rip's job exists from here on; its "preparing" status is done.
        iso_prepare.clear(drive.id)
        # A new disc: the note about the last one no longer applies.
        drive.notice = None

    async def _load_config(self) -> Config:
        return (await self.session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one()

    def _reject_if_paused(self, cfg: Config) -> None:
        if pause_refuses_new_jobs(cfg):
            raise RippingPausedError()

    async def _apply_previously_ripped_policy(self, drive: Drive, cfg: Config, scan: ScanResult) -> Job | None:
        """Returns the earlier rip to hold the disc against, or None; raises the 409 on reject."""
        # A disc ARM already ripped (on any drive) is held, rejected or ripped
        # again per on_previously_ripped. A reused job was already through this.
        previous: Job | None = None
        action = cfg.on_previously_ripped or PreviouslyRippedAction.HOLD
        if self.reuse_job is None and action != PreviouslyRippedAction.RIP:
            earlier = await find_previous_rips(self.session, fingerprints=self.fps)
            armed = [j for j in earlier if flag_is_set(j.metadata_json, "rerip_allowed")]
            if armed:
                # The operator chose "Rip again" on an earlier rip of this disc
                # (any of them, not only the newest): let this one through, once.
                for j in armed:
                    j.metadata_json = with_flags(j.metadata_json, rerip_allowed=False)
                    self.session.add(j)
                logger.info("identify drive_id=%s: rip again of %s allowed once", drive.id, armed[0].id)
            elif earlier:
                previous = earlier[0]
            if previous is not None and action == PreviouslyRippedAction.REJECT:
                await _record_duplicate_rejection(self.session, self.hub, drive, previous, scan)
                raise DiscAlreadyRippedError(previous.id)
        return previous

    async def _reuse_or_create_job(self, drive: Drive, cfg: Config, scan: ScanResult) -> Job:
        if self.reuse_job is not None:
            job = self.reuse_job
            # Guard 1 (no identity clobber): never re-run the dispatcher or overwrite
            # title/year/poster/metadata on a reused job. The operator may have manually
            # set or corrected the identity (e.g. AWAITING_USER_ID title); a re-scan
            # must not clobber it. Only refresh scan_result in metadata_json (below).
            self.already_identified = True
            self.prior_status = job.status
        else:
            job = Job(
                drive_id=self.req.drive_id,
                drive_serial=drive.serial,
                disc_type=scan.disc_type,
                status=JobStatus.CREATED,
                tick_one_version=cfg.tick_one_version if scan.disc_type in VIDEO_DISC_TYPES else None,
            )
            self.session.add(job)
            await self.session.flush()
            self.already_identified = False
            self.prior_status = None
        return job

    async def _fail_scan(self, job: Job, failure: ScanFailure) -> None:
        """The disc could not be scanned: fail the job with the reason; there is nothing to fingerprint or identify."""
        await fail_job(self.session, self.hub, job, scan_failure_text(failure))
        await self.session.refresh(job)

    async def _persist_fingerprints(self, job: Job, scan: ScanResult) -> None:
        # Persist every fingerprint the ripper computed. The (job_id, algo)
        # unique constraint plus per-scan dedup means re-runs of identify on
        # the same disc are idempotent.
        # Guard 2 (no fingerprint re-insert): on reuse, pre-load existing algos so we
        # skip any (job_id, algo) pair already stored — avoids uq_disc_fingerprints_job_algo
        # IntegrityError without switching to pg_insert.
        existing_algos: set[str] = set()
        if self.reuse_job is not None:
            existing_fp_rows = (
                (await self.session.execute(select(DiscFingerprint).where(col(DiscFingerprint.job_id) == job.id)))
                .scalars()
                .all()
            )
            existing_algos = {r.algo for r in existing_fp_rows}
        seen_algos: set[str] = set()
        for fp in scan.fingerprints:
            if not fp.algo or not fp.value:
                continue
            algo = fp.algo.lower()
            if algo in seen_algos or algo in existing_algos:
                continue
            seen_algos.add(algo)
            self.session.add(DiscFingerprint(job_id=job.id, algo=algo, value=fp.value))
        await self.session.flush()

    async def _lookup_thediscdb(self, job: Job, scan: ScanResult) -> DiscMatch | None:
        store = self.thediscdb_store
        content_hash = next(
            (fp.value for fp in scan.fingerprints if fp.algo.lower() == "thediscdb" and fp.value),
            None,
        )
        match: DiscMatch | None = None
        if store is not None and content_hash:
            try:
                match = await asyncio.to_thread(store.lookup, content_hash)
                if match is not None:
                    put_source(job, THEDISCDB, build_claims(match, scan, now=datetime.now(timezone.utc)))
                    logger.info("thediscdb: matched release=%s", match.release_slug)
            except Exception as e:
                logger.warning("thediscdb: lookup failed job_id=%s: %s", job.id, e)
                match = None
        return match

    async def _adopt_pending_session(self, job: Job) -> None:
        # pending_session_id must land BEFORE anything below that resolves
        # the job's rip preset — persist_review_tracks (hold_for_review branch)
        # resolves via resolve_rip_preset_for_job -> resolve_routed_session_id, which
        # reads this column. Assigning it after would mean a manual-trigger
        # rip with an explicit session and hold_for_review on would persist review
        # tracks chosen by the drive/disc-type default preset instead of the routed
        # session's preset — the exact held-vs-unattended divergence
        # resolve_rip_preset_id_for_job's docstring promises never happens.
        if self.req.pending_session_id is not None:
            # The ripper echoes the session chosen at manual trigger; it can have
            # been deleted since. Writing a dangling id into the FK column would
            # turn this identify into a 500 the ripper retries forever, so drop
            # it and let routing fall back to the routes / drive default.
            chosen = (
                await self.session.execute(select(Session).where(col(Session.id) == self.req.pending_session_id))
            ).scalar_one_or_none()
            if chosen is None:
                logger.warning(
                    "identify job_id=%s: pending session %s no longer exists; ignoring it",
                    job.id,
                    self.req.pending_session_id,
                )
            else:
                job.pending_session_id = self.req.pending_session_id

    async def _collected(self, call: Awaitable[_T]) -> _T:
        try:
            return await call
        finally:
            self.attempts.extend(self.dispatcher.last_attempts)

    def _exact(self, scan: ScanResult, hit: MetadataResult, how: str) -> Identification:
        """A hit found by an exact route (TheDiscDB, fingerprint): it wins, with its text score stored (D68)."""
        return self.dispatcher.explain_exact(
            scan, hit, how=how, hint_ids=[h.id for h in self.hints], iso_name=self.iso_name
        )

    async def _walk_sources(self, cfg: Config, scan: ScanResult) -> Identification:
        release: MetadataResult | None = None
        if self.thediscdb_match is not None:
            imdb = external_imdb_id(self.thediscdb_match)
            if imdb:
                kind = release_kind(self.thediscdb_match)
                if not self.dispatcher.has_imdb_lookup(cfg, kind):
                    # No enabled source can resolve the id, so no
                    # online TITLE call; the release names the disc.
                    # Held, not returned yet: the fingerprint database
                    # below needs no key either, so a keyless install
                    # would otherwise never reach the one source it can
                    # use. The weighted title search IS skipped: it would
                    # re-rank this exact content-hash match.
                    release = release_result(self.thediscdb_match, imdb)
                else:
                    exact = await self._collected(self.dispatcher.identify_from_imdb(imdb, cfg, kind=kind))
                    if exact is not None:
                        return self._exact(scan, exact, "thediscdb")
        if release is not None:
            fingerprint = await self._collected(self.dispatcher.identify_from_fingerprint(scan, cfg))
            return (
                self._exact(scan, fingerprint, "fingerprint")
                if fingerprint
                else self._exact(scan, release, "thediscdb")
            )
        return await self._collected(
            self.dispatcher.identify(scan, cfg, hint_ids=[h.id for h in self.hints], iso_name=self.iso_name)
        )

    async def _dispatch(self, job: Job, cfg: Config, scan: ScanResult) -> None:
        # Every source the exact and the fuzzy walks tried, kept on a miss so
        # the review card can say why the automatic match missed. The
        # dispatcher keeps each call's attempts in the calling task's context,
        # so they are read here, inside the task that ran the call: after it
        # returns, or as wait_for cancels it when the whole dispatch times out.
        self.attempts = []

        try:
            identification = await asyncio.wait_for(self._walk_sources(cfg, scan), timeout=DISPATCH_TIMEOUT_SECONDS)
            self.result, self.match = identification.result, identification.match
            self.timed_out = False
        except asyncio.TimeoutError:
            logger.info("identify dispatch_timeout")
            self.result = None
            self.match = None
            self.timed_out = True
            self.attempts.append(
                {
                    "source": None,
                    "step": "title",
                    "kind": None,
                    "outcome": "timeout",
                    "detail": f"lookup took longer than {DISPATCH_TIMEOUT_SECONDS:g} s",
                }
            )

    def _miss_title(self, scan: ScanResult) -> str | None:
        release_title = release_identity(self.thediscdb_match)[0] if self.thediscdb_match is not None else None
        # The cleaned hint titles are search inputs only: a miss (or a held
        # hit) is named by the disc's own BDMT name as written, else the
        # release, else the label.
        bdmt_name = (
            scan.bd_meta.name.strip()
            if scan.bd_meta is not None and any(h.id == "bd_title" for h in self.hints)
            else ""
        )
        return bdmt_name or release_title or scan.volume_label

    def _record_identify_sections(self, job: Job) -> None:
        # The miss reasons belong to a miss only; any hit (applied or held)
        # leaves no list behind. The match breakdown is the opposite: it is
        # kept after an apply, and a re-identify replaces it.
        metadata = {
            k: v for k, v in (job.metadata_json or {}).items() if k not in ("identify_attempts", "identify_match")
        }
        if self.result is None and not self._is_shortlist():
            # The most recent ones; a whole-dispatch timeout entry is last.
            metadata["identify_attempts"] = self.attempts[-MAX_IDENTIFY_ATTEMPTS:]
        if self.match is not None:
            metadata["identify_match"] = self.match.model_dump(mode="json", exclude_none=True)
            logger.info(log_line(job.id, self.match))
        job.metadata_json = metadata

    def _is_shortlist(self) -> bool:
        return self.match is not None and self.match.decision == "shortlist" and self.match.shortlist > 0

    async def _save(self, job: Job, scan: ScanResult) -> None:
        job.metadata_json = {
            **(job.metadata_json or {}),
            "scan_result": scan.model_dump(mode="json"),
        }

        await self.session.commit()
        await self.session.refresh(job)

    async def _emit_held_event(self, job: Job, scan: ScanResult) -> None:
        if job.status in (JobStatus.AWAITING_USER_ID, JobStatus.AWAITING_REVIEW):
            # awaiting_user_id -> needs identification; awaiting_review -> held for the
            # timed review gate. Distinct event types so the dashboard can label them.
            # WS-transition guard: only emit if this is a real status transition — do
            # not re-emit for a reused job already sitting in the target held status.
            if self.reuse_job is None or self.prior_status != job.status:
                event_type = (
                    "rip.needs_user_input" if job.status == JobStatus.AWAITING_USER_ID else "rip.awaiting_review"
                )
                payload: dict[str, object] = {
                    "job_id": job.id,
                    "drive_id": job.drive_id,
                    "volume_label": scan.volume_label,
                    "disc_type": job.disc_type.value,
                }
                if self.previous is not None:
                    payload["previous_job_id"] = self.previous.id
                await self.hub.emit(
                    topic="ripper.events",
                    event_type=event_type,
                    payload=payload,
                    job_id=job.id,
                    session=self.session,
                )
                await self.session.commit()

    async def _schedule_episode_stage(self, job: Job) -> None:
        # Background episode stage trigger: only after the final commit
        # above (whichever branch made it), and only when it's worth the async
        # DB round-trip — the runner itself re-checks is_tv_candidate against
        # freshly loaded tracks before doing any work.
        if self.stage_runner is not None:
            stage_tracks = (
                (await self.session.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all()
            )
            if is_tv_candidate(job, stage_tracks):
                self.stage_runner.schedule(job.id)

    def _is_ambiguous_toc(self, result: MetadataResult | None) -> bool:
        # A CD matched only by track layout where several releases fit is a
        # guess between pressings: hold it for the operator whatever the
        # music auto-apply switch says.
        return (
            result is not None
            and result.provider == "musicbrainz"
            and len(result.payload.get("toc_candidates") or []) > 1
        )

    async def _apply_hit(self, job: Job, cfg: Config, scan: ScanResult, result: MetadataResult) -> None:
        apply_identity_result(job, result, now=datetime.now(timezone.utc))
        # Timed review gate: a GENUINELY identified disc (result is not None — not
        # the block_on_miss=false synthetic "unidentified" IDENTIFIED below) parks
        # for operator review when hold_for_review is on, stamping the countdown
        # anchor and persisting the scan's titles as Track rows so the review UI
        # shows the full title list. Otherwise it proceeds straight to rip as
        # today (tracks created at rip-start).
        if cfg.hold_for_review:
            job.status = JobStatus.AWAITING_REVIEW
            job.wait_start_time = datetime.now(timezone.utc)
            await persist_review_tracks(self.session, job, scan)
        else:
            job.status = JobStatus.IDENTIFIED
        job_events.log_identified(
            job, result.provider or "unknown", self._hit_method(result), first_str((result.payload or {}).get("artist"))
        )

    async def _hold_hit(
        self, job: Job, scan: ScanResult, result: MetadataResult, miss_title: str | None, ambiguous_toc: bool
    ) -> None:
        # This kind's "Apply confident matches" switch is off. Keep
        # the hit for the operator to confirm; the disc waits with no
        # countdown (the ripper treats a null wait_start_time as "no
        # countdown") and stays unidentified until they accept or
        # resolve it. The review gate's own countdown never starts here.
        job.title = miss_title
        top = self.match.candidates[0] if self.match is not None and self.match.candidates else None
        job.metadata_json = suggest_identity(
            job.metadata_json,
            result,
            now=datetime.now(timezone.utc),
            reason="ambiguous_toc" if ambiguous_toc else "auto_apply_off",
            score=top.score if top is not None else None,
        )
        job.status = JobStatus.AWAITING_REVIEW
        job.wait_start_time = None
        # The kind is the ROUTING input, not an identity claim: it is what
        # resolve_routed_session_id keys `session_routes` on, so the review
        # tracks below get the keep/drop defaults and preset provenance of
        # the session this disc will actually rip into. Left unset, the
        # disc routes as a never-identified one and accept never re-persists
        # the tracks, so the operator would rip the wrong set. The hit's
        # title/year/poster still reach nothing but the suggestion.
        # result.kind is a subset of MediaType's values by construction.
        job.media_type = MediaType(result.kind)
        await persist_review_tracks(self.session, job, scan)
        job_events.log_identify_held(job, job_events.held_hit_reason(result.kind, result.title, ambiguous_toc))

    def _hit_method(self, result: MetadataResult) -> str:
        """How the hit was found: the step of the lookup that returned it, `release` when no lookup did."""
        hits = [a for a in self.attempts if a["outcome"] == "hit" and a["source"] == result.provider]
        return hits[-1]["step"] if hits else "release"

    async def _hold_shortlist(
        self, job: Job, cfg: Config, scan: ScanResult, match: IdentifyMatch, miss_title: str | None
    ) -> None:
        """Several close titles fit: the operator picks one (D67). With `block_on_miss` the disc waits with no
        countdown, as a held hit does; without it the disc rips unidentified and the shortlist stays on the job for
        the card after the rip. Either way nothing from a candidate reaches the job's identity."""
        job.title = miss_title
        job.metadata_json = suggest_shortlist(job.metadata_json, match, now=datetime.now(timezone.utc))
        if cfg.block_on_miss:
            job.status = JobStatus.AWAITING_REVIEW
            job.wait_start_time = None
            # The top row's kind is the routing input, as for a held hit.
            job.media_type = MediaType(match.candidates[0].kind)
            await persist_review_tracks(self.session, job, scan)
        else:
            job.status = JobStatus.IDENTIFIED
        logger.info(
            "identify job_id=%s: %d close candidates shortlisted (%s)",
            job.id,
            match.shortlist,
            "waiting for the operator" if cfg.block_on_miss else "ripping unidentified",
        )

    def _apply_miss(self, job: Job, cfg: Config, miss_title: str | None) -> None:
        diagnostic: dict[str, bool] = {}
        if self.timed_out:
            diagnostic["dispatch_timeout"] = True
        if cfg.block_on_miss:
            job.status = JobStatus.AWAITING_USER_ID
            job.title = miss_title
            if diagnostic:
                job.metadata_json = with_flags(job.metadata_json, **diagnostic)
        else:
            job.status = JobStatus.IDENTIFIED
            job.title = miss_title
            job.metadata_json = with_flags(job.metadata_json, unidentified=True, **diagnostic)
        self._log_miss(job, waiting=cfg.block_on_miss)

    def _log_miss(self, job: Job, *, waiting: bool) -> None:
        provider, reason = job_events.miss_cause(self.attempts[-1] if self.attempts else None)
        job_events.log_not_identified(job, provider, reason, waiting=waiting)

    async def _hold_previously_ripped(self, job: Job, scan: ScanResult, previous: Job) -> None:
        # on_previously_ripped=hold: whatever identify concluded, the disc
        # waits for Rip again or Discard. No countdown (wait_start_time
        # stays unset), so the ripper never auto-starts it.
        if job.status != JobStatus.AWAITING_REVIEW:
            await persist_review_tracks(self.session, job, scan)
        job.status = JobStatus.AWAITING_REVIEW
        job.wait_start_time = None
        job.metadata_json = {
            **(job.metadata_json or {}),
            "previously_ripped": {"job_id": previous.id},
        }
        job_events.log_identify_held(job, job_events.previously_ripped_reason(previous.id))

    async def _identify_new_disc(self, job: Job, cfg: Config, scan: ScanResult) -> None:
        await self._dispatch(job, cfg, scan)
        miss_title = self._miss_title(scan)
        self._record_identify_sections(job)

        result = self.result
        ambiguous_toc = self._is_ambiguous_toc(result)
        if result is not None and not ambiguous_toc and auto_apply_for(cfg, result.kind):
            await self._apply_hit(job, cfg, scan, result)
        elif result is not None:
            await self._hold_hit(job, scan, result, miss_title, ambiguous_toc)
        elif self.match is not None and self._is_shortlist():
            await self._hold_shortlist(job, cfg, scan, self.match, miss_title)
        else:
            self._apply_miss(job, cfg, miss_title)

        if self.previous is not None:
            await self._hold_previously_ripped(job, scan, self.previous)

        # Apply every stored proposal: hint job fields for all outcomes, plus
        # disc-map / preset track fields when review tracks were persisted.
        await resolve_job(self.session, job)

    async def run(self) -> Job:
        self.drive = drive = await self._load_drive()
        self._mark_new_disc(drive)

        self.cfg = cfg = await self._load_config()

        self._reject_if_paused(cfg)

        self.scan = scan = self.req.scan_result
        self.fps = [(fp.algo.lower(), fp.value) for fp in scan.fingerprints if fp.algo and fp.value]
        # A virtual drive holds one source for its whole life: its parked job is this disc's.
        decision = await find_reusable_job_for_disc(
            self.session,
            drive_id=self.req.drive_id,
            fingerprints=self.fps,
            same_source=drive.kind == DriveKind.VIRTUAL,
        )
        if decision is not None and decision.action == "in_flight":
            # Disc re-scanned while its rip is in flight (restart race) — return the
            # live job; in-flight recovery owns it. No new job, no re-identify.
            return decision.job
        self.reuse_job = decision.job if decision is not None and decision.action == "reuse" else None

        self.previous = await self._apply_previously_ripped_policy(drive, cfg, scan)

        self.job = job = await self._reuse_or_create_job(drive, cfg, scan)
        with with_log_context(job_id=job.id):
            return await self._identify_job(job, drive, cfg, scan)

    async def _identify_job(self, job: Job, drive: Drive, cfg: Config, scan: ScanResult) -> Job:
        if scan.failure is not None:
            await self._fail_scan(job, scan.failure)
            return job

        await self._persist_fingerprints(job, scan)

        self.hints = enabled_hint_sources(cfg)
        self.iso_name = source_name_of(drive)
        if not self.already_identified:
            # Offline disc hints (volume label, Blu-ray BDMT title, ISO file name): season / disc /
            # total proposals plus a cleaner search title for the dispatcher, in
            # the operator's configured source order.
            run_disc_hints(job, scan, now=datetime.now(timezone.utc), sources=self.hints, source_name=self.iso_name)

        self.thediscdb_match = None
        if not self.already_identified and cfg.thediscdb_enabled:
            self.thediscdb_match = await self._lookup_thediscdb(job, scan)

        await self._adopt_pending_session(job)

        if self.already_identified:
            # Guard 1: preserve existing identity — do not re-run the dispatcher or
            # overwrite title/year/poster/metadata set by the previous identify run.
            self.result = None
            self.timed_out = False
        else:
            await self._identify_new_disc(job, cfg, scan)

        await self._save(job, scan)
        await self._emit_held_event(job, scan)
        await self._schedule_episode_stage(job)
        return job
