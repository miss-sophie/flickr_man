import flickrapi
import argparse
import subprocess
import logging
import os
import sys
import wget
import json
import configparser
from pick import pick
from pprint import pprint as print
from retrying import retry
import shutil
from progress.bar import IncrementalBar
import time
import datetime

flickr = None
Config = configparser.ConfigParser()

photos_queued = None
photos_processed_and_modified = []
photos_processed_not_modified = []
upload_failed = []

callback_bar = None


class ExifTool(object):

    sentinel = "{ready}\n"

    def __init__(self, executable="/usr/bin/exiftool"):
        self.executable = executable

    def __enter__(self):
        self.process = subprocess.Popen(
            [self.executable, "-stay_open", "True", "-@", "-"],
            universal_newlines=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.process.stdin.write("-stay_open\nFalse\n")
        self.process.stdin.flush()

    def execute(self, *args):
        args = args + ("-execute\n",)
        self.process.stdin.write(str.join("\n", args))
        self.process.stdin.flush()
        output = ""
        fd = self.process.stdout.fileno()
        while not output.endswith(self.sentinel):
            output += os.read(fd, 4096).decode('utf-8')
        return output[:-len(self.sentinel)]

    def get_metadata(self, filename):
        return json.loads(self.execute("-G", "-j", "-n", filename))

    def write_metadata(self, filename, metadata_file):
        metadata = "-json=" + metadata_file
        return self.execute("-n", metadata, filename)


def callback(progress):
    global callback_bar
    if progress == 00:
        callback_bar = IncrementalBar('Uploading', max=100)
    elif progress == 100:
        callback_bar.finish()
    else:
        callback_bar.goto(progress)


class FileWithCallback(object):
    def __init__(self, filename, callback):
        self.file = open(filename, 'rb')
        self.callback = callback
        # the following attributes and methods are required
        self.len = os.path.getsize(filename)
        self.fileno = self.file.fileno
        self.tell = self.file.tell

    def read(self, size):
        if self.callback:
            self.callback(self.tell() * 100 // self.len)
        return self.file.read(size)


def modify_exif(filename, old_value, new_value):
    """
    Modifies the exif-data of the given photo.
    :param filename:
    :param old_value:
    :param new_value:
    :return: boolean modified
    """
    modified = False
    file, file_extension = os.path.splitext(filename)
    #.png don't contain exif-tags
    if file_extension == '.jpeg' or file_extension == '.jpg' or file_extension == '.tiff':
        with ExifTool() as exif:
            metadata = exif.get_metadata(filename)

            for key in metadata[0].keys():
                if metadata[0][key] == old_value:
                    metadata[0][key] = new_value
                    print('Changed ' + key)
                    modified = True
            if modified:
                metadata_file = file + '.json'
                with open(metadata_file, 'w') as x:
                    json.dump(metadata, x)
                exif.write_metadata(filename, metadata_file)
    return modified


@retry()
def set_date_posted(photo_id, date_posted):
    try:
        flickr.photos.setDates(photo_id=photo_id, date_posted=date_posted)
    except flickrapi.FlickrError as fe:
        logging.critical(fe)


@retry()
def get_exif(photo_id):
    try:
        exif_response = flickr.photos.getExif(photo_id=photo_id)
        exif_list = []
        for exif in exif_response['photo']['exif']:
            exif_tag = exif['tag']
            exif.remove('tag')
            exif_dict = dict(exif_tag, exif)
            exif_list.append(exif_dict)
        return
    except flickrapi.FlickrError as f_error:
        logging.ERROR(f_error)


@retry()
def get_info(photo_id):
    try:
        info_response = flickr.photos.getInfo(photo_id=photo_id)
        return info_response
    except flickrapi.FlickrError as f_error:
        logging.ERROR(f_error)


@retry()
def get_user_id_by_username(username):
    try:
        print('Fetching user id...')
        response = flickr.people.findByUsername(username=username)
    except flickrapi.exceptions.FlickrError as error:
        logging.info(error)
        return None
    u_id = response['user']['nsid']
    logging.debug('nsid:' + u_id)
    if u_id is None:
        print('User not found.')
        exit(1)
    return u_id


def get_photos_from_photoset(user_id, photoset_id):
    try:
        response = flickr.photosets.getPhotos(photoset_id=photoset_id, user_id=user_id)
        total_photos = response['photoset']['total']
        total_pages = response['photoset']['pages']
        logging.debug("Pages found: " + str(total_pages))
        photos = []
        page = 1
        while page <= total_pages:
            response = flickr.photosets.getPhotos(photoset_id=photoset_id, user_id=user_id, extras="url_o", page=page)
            photos.extend(response['photoset']['photo'])
            logging.debug("Current page: " + str(response['photoset']['page']))
            page += 1
        if len(photos) == int(total_photos):
            return photos
        else:
            return None
    except flickrapi.exceptions.FlickrError as error:
        logging.info(error)
        return None


def get_all_photos_from_user(user_id):
    '''
    :param user_id:
    :return: List of dicts with photo_id and url_o [{<id>: <url_o>}...]
    '''
    try:
        response = flickr.people.getPhotos(user_id=user_id, extras="url_o")
        total_photos = response['photos']['total']
        total_pages = response['photos']['pages']
        logging.debug("Pages found: " + str(total_pages))
        photos = []
        page = 1
        while page <= total_pages:
            response = flickr.people.getPhotos(user_id=user_id, extras="url_o", page=page)
            photos.extend(response['photos']['photo'])
            logging.debug("Current page: " + str(response['photos']['page']))
            page += 1
        if len(photos) == int(total_photos):
            return photos
        else:
            return None
    except flickrapi.exceptions.FlickrError as error:
        logging.info(error)
        return None


def get_photos(complete_account=False):
    if complete_account:
        photos =  get_all_photos_from_user(Config.get('User', 'id'))
    else:
        title = 'Please choose mode.'
        options = ['Global', 'Photoset']
        selected = pick(options, title, indicator='=>')
        mode = selected[0]
        if mode == 'Global':
            photos = get_all_photos_from_user(Config.get('User', 'id'))
        if mode == 'Photoset':
            photoset_id = choose_photoset(Config.get('User', 'id'))
            photos = get_photos_from_photoset(Config.get('User', 'id'), photoset_id)
    return photos


def get_join_date():
    try:
        join_date = flickr.profile.getProfile(user_id=Config.get('User', 'id'))['profile']['join_date']
        if join_date is not None:
            return join_date
        else:
            print('Could not fetch users join date. Please check privacy settings of your account.')
            exit(1)
    except flickrapi.FlickrError as error:
        print('Could not fetch users join date.')
        print(error)
        exit(1)


def choose_mode():
    title = 'Please choose mode.'
    options = ['Global', 'Photoset']
    selected = pick(options, title, indicator='=>')
    return selected[0]


def choose_photoset(user_id):
    try:
        print('Fetching photosets...')
        response = flickr.photosets.getList(user_id=user_id)
    except flickrapi.exceptions.FlickrError as error:
        logging.info(error)
        return None
    total_photosets = response['photosets']['total']
    logging.debug('Photosetsets found: ' + str(total_photosets))
    title = 'Please choose the photosets you want to manipulate: '
    options = response['photosets']['photoset']
    selected = pick(options,
                    title,
                    indicator='=>',
                    options_map_func=lambda option: option['title']['_content'])
    return selected[0]['id']


@retry()
def search_for_old_value(photo, old_value):
    print("Validate " + photo['id'])
    try:
        response = flickr.photos.getExif(photo_id=photo['id'])
        # logging.debug(response)
        exif_list = response['photo']['exif']
        for exif in exif_list:
            if exif['raw']['_content'] == old_value:
                logging.debug(exif)
                print("Need to modify " + photo['id'])
                return True
        print('OK ' + photo['id'])
        return False
    except flickrapi.exceptions.FlickrError as e:
        print("Could not get Exif Data.")
        print(e)
        exit(1)
    return False


@retry()
def download_image(url_0, photo_id):
    filename, file_extension = os.path.splitext(url_0)
    filename = "./downloads/" + photo_id + file_extension
    try:
        wget.download(url_0, filename)
    except Exception as e:
        logging.debug(e)
        return None
    return os.path.abspath(filename)


@retry()
def replace_image(filename, photo_id):
    fileobj = FileWithCallback(filename, callback)
    try:
        response = flickr.replace(filename=filename, fileobj=fileobj, photo_id=photo_id, format="etree")
    except Exception as e:
        logging.debug(e)
        return False
    if response.get("stat") == 'ok':
        return True
    else:
        upload_failed.append(photo_id)
        return False


def process_photo(photo, old_value, new_value):
    if photo is None:
        return False
    if old_value is None:
        return False
    if new_value is None:
        return False
    if search_for_old_value(photo, old_value):
        filename = download_image(photo['url_o'], photo['id'])
        if filename is None:
            return False
        if modify_exif(filename, old_value, new_value):
            return replace_image(filename, photo['id'])
        return False


def pre_routine():
    global Config
    # make sure the download directory is in place.
    if not os.path.exists('downloads'):
        os.mkdir('downloads')
    # make sure exiftool is installed
    if not os.path.exists('/usr/bin/exiftool'):
        print('Cloud not find exiftool. (/usr/bin/exiftool)')
        exit(1)
    # load config
    if not os.path.isfile('config.ini'):
        # No config file found. Generating base file
        configfile = open('config.ini', 'w')
        Config.add_section('Api')
        Config.set('Api', 'key', 'yourkey')
        Config.set('Api', 'secret', 'yoursecret')
        Config.add_section('User')
        Config.set('User', 'id', 'yourid')
        Config.set('User', 'name', 'yourname')
        Config.write(configfile)
        configfile.close()
    try:
        Config.read('config.ini')
        # TODO Sanititze confige file
    except configparser.ParsingError as pe:
        print('Config file corrupted.')
        print(pe)
        exit(1)
    # initialize FlickerApi
    global flickr
    flickr = flickrapi.FlickrAPI(Config.get('Api', 'key'), Config.get('Api', 'secret'), token=None, format="parsed-json", store_token=False)
    return


def post_routine():
    print('Do you want to keep the working files in ./downloads?')
    answer = input('yes/no')
    if answer  == "no":
        print('Deleting files...')
        shutil.rmtree('downloads')
        return True
    if answer == 'yes':
        print('I don´t touch the files.')
        return True
    return False


def auth():
    try:
        token = flickr.authenticate_via_browser(perms='write')
        logging.debug(token)
    except flickrapi.FlickrError as fe:
        logging.warning(fe)
        exit(1)


def config(args: dict) -> None:
    # View config
    if args.view:
        print("Exif-Manipulator Config:")
        for section in Config.sections():
            print("[" + section + "]")
            for (key, val) in Config.items(section):
                print(key + ": " + val)
        return
    # Set config
    if args.set:
        modified = False
        if args.userid is not None:
            Config.set('User', 'id', args.userid)
            modified = True
        if args.username is not None:
            userid = get_user_id_by_username(args.username)
            # TODO None Check and workaround
            Config.set('User', 'id', userid)
            Config.set('User', 'name', args.username)
            modified = True
        if args.apikey is not None:
            if args.apisecret is not None:
                Config.set('Api', 'key', args.apikey)
                Config.set('Api', 'key', args.apisecret)
                modified = True
            else:
                print('Please provide a suitable Secret to your key')
                exit(1)
        if modified:
            configfile = open('config.ini', 'w')
            Config.write(configfile)
            configfile.close()
        return


def modify(args: dict) -> dict:
    auth()
    photos = get_photos(args.all)
    if photos is not None:
        progress_bar = IncrementalBar('Processing', max=len(photos))
        for photo in photos:
            print('Processing: ' + photo['id'])
            processed = process_photo(photo=photo, old_value=args.old, new_value=args.new)
            if processed:
                photos_processed_and_modified.append(photo['id'])
            else:
                photos_processed_not_modified.append(photo['id'])
            progress_bar.next()
        progress_bar.finish()
    total_processed = len(photos_processed_not_modified) + len(photos_processed_and_modified)
    if len(photos) == total_processed:
        print('Done. Photos processed: ')
        print(total_processed)
        print('Photos modified: ' + str(len(photos_processed_and_modified)))
        print('Photos not modified: ' + str(len(photos_processed_not_modified)))
        print('Upload failed:' + str(len(upload_failed)))
    status_file = 'status.txt'
    with open(status_file, 'w') as x:
        x.write("Modified:\n")
        for item in photos_processed_and_modified:
            x.write("%s\n" % item)
        x.write("Not Modified:\n")
        for item in photos_processed_not_modified:
            x.write("%s\n" % item)
        x.write("Upload failed:\n")
        for item in upload_failed:
            x.write("%s\n" % item)
    post_routine()
    return


def sort(args: dict) -> dict:
    auth()
    min_date = int(get_join_date())
    photos = get_photos(args.all)
    photo_info = []
    logging.info('Fetch Photo Info')
    fetch_bar = IncrementalBar('Fetch Photo Info-Set', max=len(photos))
    for photo in photos:
        info = get_info(photo['id'])
        info_dict = {
            'id': photo['id'],
            # Convert SQL Date to Unix Timestamp
            'date_taken': int(time.mktime(datetime.datetime.strptime(info['photo']['dates']['taken'], '%Y-%m-%d %X').timetuple())),
            'date_uploaded': int(info['photo']['dateuploaded']),
            'date_posted': int(info['photo']['dates']['posted']),
        }
        photo_info.append(dict(info_dict))
        fetch_bar.next()
    fetch_bar.finish()
    photo_info.sort(key=lambda k: k['date_taken'])
    logging.info('Sorting Photos...')
    logging.debug(photo_info)

    bar = IncrementalBar('Sorting', max=len(photo_info))
    for photo in photo_info:
        if photo['date_taken'] <= min_date:
            photo['date_posted'] = min_date
            min_date += 1
        else:
            photo['date_posted'] = photo['date_taken']
        set_date_posted(photo['id'], photo['date_posted'])
        bar.next()
    bar.finish()


def start():
    class ExifInitParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write('error: %s\n' % message)
            self.print_help()
            sys.exit(2)

    print('Exif-Manipulator for Flickr v.0.1')
    parser = ExifInitParser(description='Exif-Manipulator for Flickr')

    subparsers = parser.add_subparsers()

    # create the parser for 'config' command
    config_parser = subparsers.add_parser('config')
    config_mode_group = config_parser.add_argument_group('Mode selector')
    config_mode_group.add_argument('--view', help="Show the current config", action="store_true")
    config_mode_group.add_argument('--set', help="Set the specified value", action="store_true")
    config_user_group = config_parser.add_argument_group('User Settings')
    config_user_group.add_argument('-id', '--userid', type=str, help='Your Flickr NS ID')
    config_user_group.add_argument('-name', '--username', type=str, help='Your Flickr display name e.g. Max Muster')
    config_auth_group = config_parser.add_argument_group('Api Authentication')
    config_auth_group.add_argument('-k', '--apikey', type=str, help='Your Flicker API Key')
    config_auth_group.add_argument('-s', '--apisecret', type=str, help='Your Flicker API Secret')
    config_parser.set_defaults(func=config)

    # create the parser for 'modify' command
    modify_parser = subparsers.add_parser('modify')
    modify_parser.add_argument('old_value', metavar='old', type=str, help='Exif value to search for')
    modify_parser.add_argument('new_value', metavar='new', type=str, help='Replacing Exif value')
    modify_parser.add_argument('--all', help='Iterates through the complete account.', action="store_true")
    modify_parser.add_argument('--checkonly', help='Perform run without changing the photos.', action="store_true")
    modify_parser.set_defaults(func=modify)

    # create the parser for 'sort' command
    sort_parser = subparsers.add_parser('sort')
    sort_parser.add_argument('--all', help='Iterates through the complete account.', action="store_true")
    sort_parser.set_defaults(func=sort)

    args = parser.parse_args()
    args.func(args)


def main():
    pre_routine()
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    start()


if __name__ == "__main__":
    main()
