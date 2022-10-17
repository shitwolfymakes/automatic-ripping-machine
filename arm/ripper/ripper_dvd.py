
def rip(job, logfile):
    # PREP JOB DATA
    # Set the sub-folder type - (movie|tv|unknown)
    # Fix the job title - Title (Year) | Title

    # CHECK FOR INVALID CONDITIONS
    # check if duplicates are allowed
    #     return with non-zero code if not to enable testing
    # check if 99 track rips are allowed - IF THIS DISK HAS 99 TRACK PROTECTION, THAT SHOULD ALREADY BE STORED IN JOB
    #     return with non-zero code if not to enable testing

    # RIP WITH MAKEMKV
    # create raw directory for rip output
    # set staging directory path to raw directory output
    # ALWAYS RIP WITH MAKEMKV, MORE WORK BUT LESS HASSLE WHEN HANDLING

    # TRANSCODE WITH HANDBRAKE
    # if not SKIP_TRANSCODING
    #     create transcode output directory
    #     transcode files in staging directory into transcode output directory
    #     set staging directory path to transcode output directory path

    # SAVE PROCESSED DATA
    # Create final output directory, using the current job title (NO NEED TO CORRECT SINCE THIS IS WHEN WE CREATE IT)
    # copy files from staging directory to final output directory
    # Save poster image from disc if enabled - MOVE THIS TO MAIN

    # CLEAN UP FILES
    # if DEL_RAW_FILES
    #     delete raw directory
    # if not SKIP_TRANSCODING
    #     delete transcode directory
    pass
