FROM debian:jessie

RUN apt-get update && apt-get install -y python3 git python3-pip \
	libmysqlclient-dev libpq-dev locales build-essential python3-dev \
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
    cd /src && \
    pip3 install -U pip setuptools wheel && \
    pip3 install -r requirements.txt && \
    pip3 install gunicorn mysqlclient && \
    python3 manage.py collectstatic --noinput && \
    chmod +x /usr/local/bin/pretalx

RUN mkdir /data
VOLUME /data

EXPOSE 80
ENTRYPOINT ["/usr/local/bin/pretalx"]