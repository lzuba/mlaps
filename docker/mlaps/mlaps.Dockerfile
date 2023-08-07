FROM python:3.10-bullseye

RUN apt update && apt install mycli -y
COPY requirements.txt /mlaps/
RUN pip install --no-cache-dir -r /mlaps/requirements.txt

COPY /app /mlaps/app
COPY docker/mlaps/wait-for-mysql.sh /mlaps
WORKDIR /mlaps

CMD ["bash","wait-for-mysql.sh"]
