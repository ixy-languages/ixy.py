import sys
import argparse
import time
import logging
import subprocess
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler, FileSystemEventHandler


class RsyncEventHandler(FileSystemEventHandler):
    def __init__(self, host, src_dir, dst_dir, flags, exclude):
        self.host = host
        self.src = src_dir
        self.dst = dst_dir
        self.flags = flags
        self.exclude = exclude
        self.sync()

    def on_any_event(self, event):
        if not event.is_directory:
            self.sync()

    def sync(self):
        cmd = ['rsync', self.flags, self.src, '--exclude-from', self.exclude, '{}:{}'.format(self.host, self.dst)]
        print(' '.join(cmd))
        subprocess.call(cmd)


def main(args):
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    event_handler = LoggingEventHandler()
    rsync_handler = RsyncEventHandler(args.host, args.source, args.destination, args.rsync, args.exclude_file)
    observer = Observer()
    observer.schedule(event_handler, args.source, recursive=True)
    observer.schedule(rsync_handler, args.source, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('host', type=str, help='Host')
    parser.add_argument('destination', type=str, help='Destination directory')
    parser.add_argument('-s', '--source', type=str, default='.', help='Source directory (default current directory)')
    parser.add_argument('-rs', '--rsync', type=str, default='-azvq', help='rsync flags (default -avzq')
    parser.add_argument('-ef', '--exclude-file', type=str, default='.rsync-exclude', help='File containing exclusion rules (default .gitignore)')
    args = parser.parse_args()
    main(args)
