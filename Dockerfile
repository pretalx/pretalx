FROM python:3.6

RUN apt-get update && apt-get install -y git gettext \
	libmysqlclient-dev libpq-dev locales libmemcached-dev build-essential \
	--no-install-recommends && \
	apt-get clean && \
	rm -rf /var/lib/apt/lists/* && \
    dpkg-reconfigure locales && \
	locale-gen C.UTF-8 && \
	/usr/sbin/update-locale LANG=C.UTF-8

ENV LC_ALL C.UTF-8

COPY docker/pretalx.bash /usr/local/bin/pretalx
COPY src /src

RUN pip3 install -U pip setuptools wheel typing && \
    pip3 install -e src/ && \
    pip3 install django-redis pylibmc mysqlclient psycopg2-binary && \
    pip3 install gunicorn && \
    chmod +x /usr/local/bin/pretalx

RUN groupadd -g 999 pretalx && \
    useradd -r -u 999 -g pretalx -d /src pretalx  

RUN mkdir -p /data/logs /data/media /src/static.dist

RUN python3 -m pretalx migrate && python3 -m pretalx rebuild

RUN chown -R 999:999 /data && \
    chown -R 999:999 /src/static.dist

USER pretalx
WORKDIR /src
VOLUME /data
EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/pretalx"]
CMD ["web"]
