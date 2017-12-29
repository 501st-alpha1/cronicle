import click
import glob
import logging
import os

from collections import OrderedDict
from datetime import datetime
from dateutil.relativedelta import relativedelta

from .config import config


__author__ = 'Fabrice Laporte <kraymer@gmail.com>'
__version__ = '0.1.0'
logger = logging.getLogger(__name__)

# Names of frequency folders that will host symlinks, and minimum number of days between 2 archives
FREQUENCY_FOLDER_DAYS = {
    'DAILY': 1,
    'WEEKLY': 7,
    'MONTHLY': 30,
    'YEARLY': 365,
}
CONFIG_PATH = os.path.join(config.config_dir(), 'config.yaml')


def set_logging(verbose=False):
    """Set logging level based on verbose flag.
    """
    levels = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    logger.setLevel(levels[verbose])
    ch = logging.StreamHandler()
    ch.setLevel(levels[verbose])
    ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(ch)


def get_symlinks_dates(folder, pattern='*'):
    """Return OrderedDict of symlinks sorted by creation dates (used as keys).
    """
    creation_dates = {}
    abs_pattern = os.path.join(folder, pattern)
    logger.debug('Scanning %s for symlinks' % abs_pattern)
    for x in glob.glob(abs_pattern):
        if os.path.islink(x):
            creation_dates[datetime.fromtimestamp(os.lstat(x).st_birthtime)] = x
    res = OrderedDict(sorted(creation_dates.items()))
    return res


def delta_days(folder, cfg):
    """Return nb of elapsed days since last archive in given folder.
    """
    files_dates = get_symlinks_dates(folder, cfg['pattern'])
    if files_dates:
        last_file_date = list(files_dates.keys())[-1]
        return relativedelta(datetime.now(), last_file_date).days


def symlink(filename, target, dry_run):
    """Wrapper around os.symlink that handles dry_run argument.
    """
    logger.info('Symlinking %s => %s' % (target, filename))
    if dry_run:
        return
    target_dir = os.path.dirname(target)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    os.symlink(filename, target)


def unlink(link, dry_run):
    """Wrapper around os.unlink that handles dry_run argument.
    """
    if dry_run:
        logger.info('Unlinking %s' % link)
        return
    else:
        os.unlink(link, dry_run)


def remove(filename, dry_run):
    """Wrapper around os.remove that handles dry_run argument.
    """
    if dry_run:
        logger.info('Removing %s' % filename)
        return
    else:
        os.remove(filename)


def timed_symlink(filename, ffolder, cfg, dry_run):
    """Create symlinks for filename in ffolder if enough days elapsed since last archive.
    """
    target_dir = os.path.abspath(os.path.join(os.path.dirname(filename), ffolder))
    days_elapsed = delta_days(target_dir, cfg)
    if (days_elapsed is not None) and days_elapsed < FREQUENCY_FOLDER_DAYS[ffolder]:
        logger.info('No symlink created : too short delay since last archive')
        return
    target = os.path.join(target_dir, os.path.basename(filename))

    if not os.path.lexists(target):
        symlink(filename, target, dry_run)
    else:
        logger.error('%s already exists' % target)


def rotate(filename, ffolder, cfg, _remove, dry_run=False):
    """Keep only the n last links of folder that matches same pattern than filename.
    """
    others_ffolders = set(FREQUENCY_FOLDER_DAYS.keys()) - set([ffolder])
    target_dir = os.path.abspath(os.path.join(os.path.dirname(filename), ffolder))
    links = list(get_symlinks_dates(target_dir, cfg['pattern']).values())[::-1]  # sort newest -> oldest
    numskips = cfg[ffolder.lower()]
    logger.debug('Keep %s' % (links[:numskips]))
    droplinks = links[numskips:]
    for link in droplinks:
        filepath = os.path.realpath(link)
        unlink(link, dry_run)
        if _remove and not is_symlinked(filepath, others_ffolders):
            remove(filepath, dry_run)


def is_symlinked(filepath, folders):
    """Return True if filepath has symlinks pointing to it in given folders.
    """
    dirname, basename = os.path.split(filepath)
    for folder in folders:
        target = os.path.abspath(os.path.join(dirname, folder, basename))
        if os.path.lexists(target):
            return True
    return False


def find_config(filename, cfg=None):
    """Return the config matched by filename or the default one.
    """
    res = {'daily': 0, 'weekly': 0, 'monthly': 0, 'yearly': 0, 'pattern': '*'}
    dirname, basename = os.path.split(filename)

    if not cfg:
        cfg = config
    # Overwrite default config fields with matched config ones
    for key in cfg.keys():
        abskey = os.path.join(dirname, key) if not os.path.isabs(key) else key
        for x in glob.glob(abskey):
            if x.endswith(filename):
                res.update(config[key].get())
                res['pattern'] = key
                return res


@click.command(context_settings=dict(help_option_names=['-h', '--help']),
               help=('Keep rotated time-spaced archives of a file. FILE name must match one of '
                     ' the patterns present in %s.' % CONFIG_PATH),
               epilog=('See https://github.com/Kraymer/cronicle/blob/master/README.md#usage for '
                       'more infos.'))
@click.argument('filename', type=click.Path(exists=True), metavar='FILE')
@click.option('-r', '--remove', help='Remove previous file backup when no symlink points to it.',
    default=False, is_flag=True)
@click.option('-d', '--dry-run', count=True,
              help='Just print instead of writing on filesystem.')
@click.option('-v', '--verbose', count=True)
@click.version_option(__version__)
def cronicle_cli(filename, remove, dry_run, verbose):
    set_logging(max(verbose, dry_run))
    filename = os.path.abspath(filename)
    cfg = find_config(filename)
    logger.debug('Config is %s' % cfg)
    if not cfg:
        logger.error('No pattern found in %s that matches %s.' % (
            CONFIG_PATH, filename))
        exit(1)

    for ffolder in FREQUENCY_FOLDER_DAYS.keys():
        if cfg[ffolder.lower()]:
            timed_symlink(filename, ffolder, cfg, dry_run)
            rotate(filename, ffolder, cfg, remove, dry_run)


if __name__ == "__main__":
    cronicle_cli()
