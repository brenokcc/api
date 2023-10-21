FROM python:alpine as yml-api-base
RUN apk add zlib-dev jpeg-dev build-base git libffi-dev
ADD requirements.txt /requirements.txt
RUN pip install -q --no-cache-dir -r /requirements.txt
RUN pip install -q --no-cache-dir gunicorn

FROM yml-api-base as yml-api-test
RUN pip install -q --no-cache-dir selenium
RUN apk add firefox-esr
RUN ln -sfn /usr/bin/firefox-esr /usr/bin/firefox
RUN wget -q https://github.com/mozilla/geckodriver/releases/download/v0.32.0/geckodriver-v0.32.0-linux32.tar.gz
RUN tar -xf geckodriver-v0.32.0-linux32.tar.gz
RUN chmod +x geckodriver
RUN mv geckodriver /usr/local/bin/
ENV PYTHONPATH=/var/site-packages
ADD . $PYTHONPATH/api

FROM yml-api-base as yml-api-src
ENV PYTHONPATH=/var/site-packages
ADD . $PYTHONPATH/api

FROM minidocks/weasyprint as yml-api-weasyprint
ADD ./cloud/printer.py /opt/printer.py
EXPOSE 8888
ENTRYPOINT ["python", "/opt/printer.py"]

FROM yml-api-base as yml-api
RUN pip install --no-cache-dir yml-api
