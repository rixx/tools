#!/bin/sh


set -xeuo pipefail

# Usage: BORG_PASSPHRASE= BORG_REPO= backup.sh

# export BORG_PASSPHRASE='XYZl0ngandsecurepa_55_phrasea&&123'
# export BORG_REPO=ssh://username@example.com:2022/~/backup/main

# some helpers and error handling:
info() { printf "\n%s %s\n\n" "$( date )" "$*" >&2; }
trap 'echo $( date ) Backup interrupted >&2; exit 2' INT TERM

info "Starting backup"

# Backup the most important directories into an archive named after
# the machine this script is currently running on:
/usr/bin/borg create                \
    --verbose                       \
    --filter AME                    \
    --stats                         \
    --list                          \
    --compression lz4               \
    --exclude-caches                \
    --exclude '*/node_modules'      \
    ::'{hostname}-{now}'            \
    /usr/share/webapps/pretalx/media/


backup_exit=$?

info "Pruning repository"

# Use the `prune` subcommand to maintain 7 daily, 4 weekly and 6 monthly
# archives of THIS machine. The '{hostname}-' prefix is very important to
# limit prune's operation to this machine's archives and not apply to
# other machines' archives also:

/usr/bin/borg prune                 \
    --list                          \
    --prefix '{hostname}-'          \
    --show-rc                       \
    --keep-daily    7               \
    --keep-weekly   4               \
    --keep-monthly  6               \

prune_exit=$?

# use highest exit code as global exit code
global_exit=$(( backup_exit > prune_exit ? backup_exit : prune_exit ))

/usr/bin/borg compact
compact_exit=$?

# use highest exit code as global exit code
global_exit=$(( compact_exit > global_exit ? compact_exit : global_exit ))

if [ ${global_exit} -eq 0 ]; then
    info "Backup and Prune and Compact finished successfully"
elif [ ${global_exit} -eq 1 ]; then
    info "Backup and/or Prune and Compact finished with warnings"
else
    info "Backup and/or Prune and Compact finished with errors"
fi

exit ${global_exit}
