# Setup walkthrough

The first time an admin signs in, ARM opens a short walkthrough that covers
everything a new install needs. It never duplicates Settings: each step uses the
same controls you'll find there later, so whatever you set here is what
Settings shows.

- **Your progress is saved.** Each step saves when you press **Continue**
  (drive changes save as you make them). Close the tab and ARM resumes at the
  first step you haven't finished.
- **Only the first step is required.** Every other step lets you continue even
  with a problem; it is then marked **Needs attention**.
- **Finish later** (top right) takes you to the dashboard. The walkthrough comes
  back the next time you sign in.

## 1. Secure your account

Set your own admin password. Until you do, every other part of ARM stays
locked. You can also let people on your network view ARM without signing in
(read-only). Later: **Settings, Users**.

## 2. System check

ARM checks the folders and services it was installed with:

- **Storage:** the media library, raw rips and logs folders. A folder ARM can't
  write to comes with the exact command to run on the server, for example
  `sudo chown -R 1000:1000 /home/me/arm/media`. Run it, then press
  **Check again**.
- **Ripper service:** whether ARM can start a ripper for each drive. If not,
  drives can't be enrolled until it's fixed.
- **Transcoder:** whether encoding runs on this server, on a remote host, or
  not at all (a ripper-only install).

These values come from `.env` and `docker-compose`, so fixes happen on the
server. Later: **Settings, System**.

## 3. Drives

ARM finds optical drives on its own and rescans every 30 seconds. **Enroll** a
drive to start its ripper (a few seconds), or **Ignore** a drive ARM should
leave alone. After enrolling you can give it a friendly name and say whether it
reads 4K UHD discs.

No drive at all? ARM can rip ISO image files. Set
`ARM_HOST_ISO_LIBRARY_PATH=/path/to/your/isos` in `.env`, add the mount, and
restart ARM. Later: **Settings, Drives**.

## 4. MakeMKV

Use the free beta key (ARM fetches and renews it each month) or your purchased
key. ARM can't test a key on its own: a drive's ripper checks it, and the status
line updates when it has. Two options keep Blu-ray decryption data current.
Later: **Settings, Metadata** and **Settings, Ripping**.

## 5. Find titles (optional)

Add a free TMDb or OMDb key so ARM can name your files, and press **Test** to
check it. TVDB adds TV episode numbering. TVmaze, MusicBrainz and the ARM disc
database need no key. Skip this and ARM names files from the disc label, and
you confirm titles by hand. Later: **Settings, Metadata**.

## 6. Disc handling

What happens when you insert a disc:

- **Fully automatic:** ARM identifies, rips and files it.
- **Review first:** ARM identifies the disc, then waits (60 seconds by default)
  for you to check the title before ripping. No answer and it rips anyway.
- **Manual:** nothing starts until you press Start.

This is the default for every drive; a drive can have its own setting in
**Settings, Drives**. Below it, a read-only table shows what each kind of disc
gets. Later: **Settings, Ripping** and **Settings, Sessions**.

## 7. Transcoding (optional)

Shows where encoding runs and your graphics devices. **Test encoders** runs a
short real encode on each device (10 to 60 seconds) and shows which formats
work. With no graphics device ARM encodes on the CPU. Later:
**Settings, Transcoding**.

## 8. Notifications (optional)

ARM always shows notifications in its own inbox. Pick a service (Discord,
Telegram, ntfy, email and more), fill in its details and **Send test**. You'll
hear about finished rips, rips that need you, and failures. Later:
**Notifications** and **Settings, Notifications**.

## 9. Finish

A summary of every step with a link back to it, a live "insert a disc" check,
and a **Download certificate** button so this device stops warning about ARM's
certificate.

## Afterwards

- **The dashboard checklist** lists anything skipped or needing attention. Dismiss
  it when you're done with it.
- **Settings, System, Run setup again** walks through the steps again with your
  current values filled in.
