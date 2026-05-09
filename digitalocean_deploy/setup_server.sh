#!/bin/bash

# Update system
apt update && apt upgrade -y

# Install dependencies
apt install -y python3-pip python3-venv nginx git libpq-dev

# Clone repository
cd /root
git clone https://github.com/mazedcu/school-vercel.git
cd school-vercel

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn psycopg2-binary dj-database-url whitenoise

# Collect static files
python3 manage.py collectstatic --noinput

# Set environment variables (User should do this or we can add to bashrc)
# echo "export DATABASE_URL='...'" >> ~/.bashrc
# echo "export SECRET_KEY='...'" >> ~/.bashrc
# echo "export DEBUG='False'" >> ~/.bashrc
