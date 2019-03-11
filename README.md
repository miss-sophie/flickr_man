# Flickr_Man

Flickr_Man is a Python program. He can sort your Flickr timeline chronologically by the date the photos were taken. 
He can also change exif tags. 
This can be helpful if you have changed your name or made a typo.

## Installation

### 1. Download sources
```bash
git clone https://github.com/miss-sophie/flickr_man.git
```

### 2. Setup local Python environment
Please make sure, you have Python 3 installed. Then execute the following commands.
```bash
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

### 3. Install ExifTool
Please make sure, you have [ExifTool](https://www.sno.phy.queensu.ca/~phil/exiftool/) installed.

## Configuration

### 1. Get API Credentials
Visit [Flicker App Garden](https://www.flickr.com/services/apps/create/) to obtain your API Credentials.

### 2. Setup Flickr_Man
``` bash
python flickr_man.py config --set -k <apikey> -s <apisecret>
```

### 3. Say Flickr_Man who you are
If you know you Flickr NS_ID:
``` bash
python flickr_man.py config --set -id <your-id>
```
Otherwise, tell Flicker_Man your username, which will be displayed on the landingpage of your profile.
Flickr_Man will then fetch your id.
``` bash
python flickr_man.py config --set -name <your-name>
```


## Usage
- To sort your timeline:

```bash
python flickr_man.py sort
```
- To modify exif values:
```bash
python flickr_man.py modify
```

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

## Configuration

### 1. Get Api Credentials
Visit [Flicker App Garden](https://www.flickr.com/services/apps/create/) to obtain your API Credentials.

### 2. Setup Flickr_Man
``` bash
python flickr_man.py config --set -k <apikey> -s <apisecret>
```

### 3. Say Flickr_man who you are
If you know you Flickr NS_ID:
``` bash
python flickr_man.py config --set -id <your-id>
```
Otherwise, tell Flicker_Man your username, which will be displayed on the landingpage of your profile.
``` bash
python flickr_man.py config --set -name <your-name>
```

## Usage
- To sort your timeline:

```bash
python flickr_man.py sort
```

- To modify exif values:
```bash
python flickr_man.py modify <old_value> <new_value>
```

- If you want to modify or sort your entire timeline, you can use the `--global` flag.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License
[MIT](https://choosealicense.com/licenses/mit/)
