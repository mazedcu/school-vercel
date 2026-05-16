#!/bin/bash
set -e
cd /root/school-vercel
git pull origin main
source venv/bin/activate
systemctl restart gunicorn
echo "DONE"
