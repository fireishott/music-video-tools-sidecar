# 🛠️ Troubleshooting Guide

## 📋 Quick Reference

| Issue | First Command to Run |
|-------|---------------------|
| Script won't start | `docker exec lidarr ls -la /config/extended/Video` |
| No videos downloading | `docker exec lidarr curl -s -I https://www.youtube.com` |
| Permission errors | `docker exec lidarr id abc` |
| API connection issues | `docker exec lidarr cat /config/config.xml | grep ApiKey` |
