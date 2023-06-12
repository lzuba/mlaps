FROM python:3.10-bullseye

COPY /app /mlaps/app
COPY requirements.txt /mlaps
COPY docker/mlaps/wait-for-mysql.sh /mlaps
WORKDIR /mlaps

RUN pip install --no-cache-dir -r requirements.txt
RUN apt update && apt install mycli -y

CMD ["bash","wait-for-mysql.sh"]
