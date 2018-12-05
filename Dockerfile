# THIS DOCKERFILE IS DEPRECATED
# PLEASE USE https://github.com/pretalx/pretalx-docker INSTEAD
FROM python:3.6

RUN apt-get update && apt-get install -y git gettext \
	libmariadbclient-dev libpq-dev locales libmemcached-dev build-essential \
	--no-install-recommends && \
	apt-get clean && \
	rm -rf /var/lib/apt/lists/* && \
    dpkg-reconfigure locales && \
	locale-gen C.UTF-8 && \
	/usr/sbin/update-locale LANG=C.UTF-8

ENV LC_ALL C.UTF-8

COPY docker/pretalx.bash /usr/local/bin/pretalx
COPY src /src

RUN mkdir /static && \
    pip3 install -U pip setuptools wheel typing && \
    pip3 install -e src/ && \
    pip3 install django-redis pylibmc mysqlclient psycopg2 && \
    pip3 install gunicorn && \    
    pip3 install redis==2.10.6 && \
    chmod +x /usr/local/bin/pretalx

RUN mkdir -p /data/logs /data/media
VOLUME /data

RUN python3 -m pretalx migrate && python3 -m pretalx rebuild

EXPOSE 80
ENTRYPOINT ["/usr/local/bin/pretalx"]
CMD ["web"]
