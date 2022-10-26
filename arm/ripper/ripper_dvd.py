import arm.config.config as cfg
from arm.models.models import Job
from arm.ripper import utils


def rip(job):
    """
    Top-level ripping function for dvds, be they movies or series
    :param job: The current job that is being worked on
    """
    # have_dupes, logfile, and protection can all be derived from
    # the data stored in a Job

    # PREP JOB DATA
    # Set the sub-folder type - (movie|tv|unknown)
    type_sub_folder = utils.convert_job_type(job.video_type)
    # Fix the job title - Title (Year) | Title
    job_title = utils.fix_job_title(job)

    # CHECK FOR EXCEPTION CONDITIONS
    # check if duplicates are allowed
    have_dupes = utils.job_dupe_check(job)
    if cfg.arm_config["ALLOW_DUPLICATES"] is False:
        # return with non-zero code if not to enable testing
        pass

    # check if 99 track rips are allowed - IF THIS DISK HAS 99 TRACK PROTECTION, THAT SHOULD ALREADY BE STORED IN JOB
    if cfg.arm_config["PREVENT_99"] is True:
        # return with non-zero code if not to enable testing
        pass

    # RIP WITH MAKEMKV
    # create raw directory for rip output
    # set staging directory path to raw directory output
    # construct command to run makemkv with
    # invoke makemkv_dvd with constructed command (ALWAYS RIP WITH MAKEMKV, MORE WORK BUT LESS HASSLE WHEN HANDLING)

    # TRANSCODE WITH HANDBRAKE
    # if not SKIP_TRANSCODING
    #     create transcode output directory
    #     if TRANSCODE_MAINFEATURE_ONLY
    #         construct command to run makemkv with
    #         invoke handbrake_dvd with constructed command
    #         transcode main in staging directory into transcode output directory
    #     else
    #         construct command to run makemkv with
    #         invoke handbrake_dvd with constructed command
    #         transcode files in staging directory into transcode output directory
    #     set staging directory path to transcode output directory path

    # SAVE PROCESSED DATA
    # Create final output directory, using the current job title (NO NEED TO CORRECT SINCE THIS IS WHEN WE CREATE IT)
    # copy files from staging directory to final output directory (ACCOUNT FOR TRANSCODE_MAINFEATURE_ONLY)
    # Save poster image from disc if enabled - MOVE THIS TO MAIN

    # CLEAN UP FILES
    # if DEL_RAW_FILES
    #     delete raw directory
    # if not SKIP_TRANSCODING
    #     delete transcode directory
    pass
