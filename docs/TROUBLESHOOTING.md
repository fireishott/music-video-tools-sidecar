
# Troubleshooting

## Script Won't Start
```bash
# Check if script exists
docker exec lidarr ls -la /config/extended/Video


'''bash
# Check configuration
docker exec lidarr cat /config/extended.conf

# Check if script is enabled
docker exec lidarr grep enableVideo /config/extended.conf

# Test manually
docker exec lidarr bash /config/extended/Video


## Can't Connect to Lidarr API
'''bash
# Check if Lidarr is running
docker ps | grep lidarr

# Check API key in config
docker exec lidarr cat /config/config.xml | grep ApiKey

# Verify API key in extended.conf matches
docker exec lidarr grep LidarrApiKey /config/extended.conf

# Test API connection manually
docker exec lidarr curl -s "http://localhost:8686/api/v1/system/status?apikey=YOUR_API_KEY"
No Videos Downloading
bash
# Check YouTube connectivity from container
docker exec lidarr curl -s -I https://www.youtube.com | head -n 1

# Test search manually
docker exec lidarr yt-dlp --get-title "ytsearch1:test artist official video"

# Check video folder permissions
docker exec lidarr ls -la /mnt/musicvideos/

# View script logs
docker exec lidarr cat /config/extended/logs/Video-*.log

# Watch script in action (run manually with debug)
docker exec -it lidarr bash -c "cd /config/extended && ./Video"
Permission Errors
bash
# Fix permissions for video folder (adjust UID if needed)
docker exec lidarr chown -R abc:abc /mnt/musicvideos/
docker exec lidarr chmod -R 755 /mnt/musicvideos/

# Check download folder permissions
docker exec lidarr chown -R abc:abc /config/extended/downloads/
docker exec lidarr chmod -R 755 /config/extended/downloads/

# Verify current user
docker exec lidarr id abc
Script Runs But No Videos Found
bash
# Check if artists have IMVDB links (script uses these for video discovery)
docker exec lidarr grep -r "imvdb" /config/extended/cache/imvdb/

# Test a specific artist search
docker exec lidarr yt-dlp --get-id "ytsearch5:Artist Name official music video"

# Check for missing IMVDB links log
docker exec lidarr ls -la /config/extended/logs/video/imvdb-link-missing/
Database Locked Errors
These sometimes appear in Lidarr logs but are harmless. The script only reads from Lidarr's API and does not modify the database directly.

log
[Error] EventAggregator: UpdateTrackFileService failed while processing [ArtistScannedEvent]
System.NullReferenceException: Object reference not set to an instance of an object.
If you see these, they're Lidarr internal issues and not caused by the video script.

Script Not Running Automatically
bash
# Check if scripts_init.bash is in place
docker exec lidarr ls -la /custom-cont-init.d/

# Verify custom-services.d has the script
docker exec lidarr ls -la /custom-services.d/

# Check container logs during startup
docker logs lidarr | grep -i "video\|script"
YouTube Rate Limiting
If you see errors about YouTube blocking requests:

bash
# Increase rate limit in config
# Add or modify in /config/extended.conf:
ytdlpRateLimit="5"

# Add longer delays between searches
# Add to /config/extended.conf:
youtubeFallbackDelay="5"
Still Having Issues?
Check the full container logs:

bash
docker logs lidarr
Enable debug logging in config:

bash
# Add to /config/extended.conf
logLevel="debug"
Run the script manually with verbose output:

bash
docker exec -it lidarr bash
cd /config/extended
bash -x ./Video
Open an issue on GitHub with:

Relevant log snippets

Your configuration (with API key removed)

Steps to reproduce

text
