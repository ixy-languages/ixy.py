#!/bin/bash

# an rsync script that will synchronize files every time there's a modification
# in a WATCHed location, detected through fswatch
# 										https://github.com/emcrisostomo/fswatch
# (install fswatch through brew)
#
# this script could even be more general and allow executing anything,
# not just rsync; it's actually even overkill for the way it's used, since
# rsync is simple re-launched entirely and not just for the modified file!
#
# For improved performance in remote ssh scenario, you can share ssh connections
# (eg. http://stackoverflow.com/a/20410383/422670)


# A POSIX variable
OPTIND=1         # Reset in case getopts has been used previously in the shell.

# Initialize script variables
WATCH="."
VERBOSE=1

# the wrsync
echo "wrsync v1.0 - watch and rsync"

function show_help {
	echo "$0 [-hvs] DESTINATION"
	echo ""
	echo "-h 			show this help and exit"
	echo "-v 			set verbose"
	echo "-s 			set silent mode"
	echo "-w PATH  		watch PATH (by default, it will watch current path"
	echo "DESTINATION 	in rsync form, that is SERVER:PATH"
}

# option parsing
while getopts ":hvsw:" opt; do
	case "$opt" in
		h)
			show_help
			exit 0
			;;
		v)  verbose=1
			;;
		s)	verbose=0
			;;
		w)	WATCH="$OPTARG"
			# watch a different path than the current one
			;;
		\?)
      		echo "Invalid option: -$OPTARG" >&2
      		show_help
      		;;
    esac
done

# get the reminders. We expect the DESTINATION.
shift $((OPTIND-1))  # now do something with $@

DEST="$1"

if [ -z "$DEST" ]; then
	echo "Error: missing destination" >&2
	show_help
	exit 1;
fi

# This is the real deal.
# watch...
echo "Watch '$WATCH' and sync with '$DEST'"
fswatch -e "\.tox" -e ".*___.*" -e "\.hg" -e "\.git" -e "hg" -e "vagrant" $WATCH |\
	while read file
	do
		# and rsync everything!
		echo "$file modified. Sync to $DEST"
		echo "$ rsync -azvq $WATCH ${DEST}"
		rsync -azvq $WATCH ${DEST}
#		echo "$DEST/$file sync completed"
		echo "$WATCH AND $DEST rsync completed"
	done

exit
# other way: fswatch -o -e=___ .  | xargs -n1 -I{}

# using inotify on linux. fswatch is based on

inotifywait -r -m -e close_write --format '%w%f' . |\
	while read file
	do
		echo $file
		rsync -azvq $file ${DEST}/$file
		echo -n 'Completed at '
		date
		done
