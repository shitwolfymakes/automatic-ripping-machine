from arm_common.schemas.metadata import MetadataReleaseDetail, MetadataReleaseTrack


def test_release_track_has_length_and_disc():
    t = MetadataReleaseTrack(position=1, title="Come Together", length_ms=259000, disc_number=1)
    assert t.length_ms == 259000
    assert t.disc_number == 1


def test_release_track_fields_default_none():
    t = MetadataReleaseTrack(title="X")
    assert t.length_ms is None and t.disc_number is None


def test_release_detail_has_enriched_fields():
    d = MetadataReleaseDetail(
        release_id="r1", title="Abbey Road",
        catalog_number="PCS 7088", barcode="0094638246619", country="GB",
        format="CD", status="Official", disc_count=1, track_count=17,
    )
    assert d.catalog_number == "PCS 7088"
    assert d.barcode == "0094638246619"
    assert d.country == "GB"
    assert d.format == "CD"
    assert d.status == "Official"
    assert d.disc_count == 1
    assert d.track_count == 17
