## Requirements

Container: <https://docs.linuxserver.io/images/docker-lidarr>  

## Installation/setup

1. Add 2 volumes to your container
   `/custom-services.d` and `/custom-cont-init.d` (do not map to the same local folder...)
   Docker Run Example:<br>
   `-v /path/to/preferred/local/folder-01:/custom-services.d`<br>
   `-v /path/to/preferred/local/folder-02:/custom-cont-init.d`
2. Download the [scripts_init.bash](https://github.com/fireishott/arr-scripts_Video/blob/main/lidarr/scripts_init.bash) ([Download Link](https://raw.githubusercontent.com/fireishott/arr-scripts_Video/main/lidarr/scripts_init.bash)) and place it into the following folder:
   `/custom-cont-init.d`
3. Start your container and wait for the application to load
4. Optional: Customize the configuration by modifying the following file `/config/extended.conf`
5. Restart the container

## Uninstallation/Removal  

1. Remove the 2 added volumes and delete the contents<br>
   `/custom-services.d` and `/custom-cont-init.d`
2. Delete the `/config/extended.conf` file
3. Delete the `/config/extended` folder and it's contents
4. Remove any Arr app customizations manually.

## Features

* Downloading **Music Videos** from YouTube for use in popular applications (Plex/Kodi/Emby/Jellyfin):
  * **Completely automated** - Scans your Lidarr artists and downloads official music videos
  * **Smart Search** - Searches YouTube for "[Artist] [Song] official music video" with intelligent filtering
  * **High Quality** - Downloads the best available quality up to 1080p
  * **MKV Format** - Saves videos in MKV format by default for maximum compatibility
  * **Thumbnails** - Downloads and saves high-quality YouTube thumbnails for every video
  * **Metadata** - Creates Kodi/Jellyfin/Emby compliant NFO files with complete metadata:
    * Title
    * Year (upload/release year)
    * Artist
    * MusicBrainz Artist ID
    * Genre tags from Lidarr
  * **Tag Support** - Only process artists with a specific Lidarr tag - you're in control
  * **Subtitles** - Embeds subtitles if available matching your preferred language
  * **Safe Operation** - Never deletes, renames, or modifies your existing files
  * **Optimized** - Built-in rate limiting to avoid YouTube blocks
  * **Docker First** - Works perfectly with any Lidarr Docker image

## Credits

* [LinuxServer.io Team](https://github.com/linuxserver/docker-lidarr)
* [Lidarr](https://lidarr.audio/)
* [yt-dlp](https://github.com/yt-dlp/yt-dlp)
* [ffmpeg](https://ffmpeg.org/)
* [RandomNinjaAtk](https://github.com/RandomNinjaAtk) - Original scripts that inspired this project
