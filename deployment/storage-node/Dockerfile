FROM rockylinux:9

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN dnf -y update \
 && dnf -y install python3.11 python3.11-pip ca-certificates shadow-utils \
 && dnf clean all \
 && rm -rf /var/cache/dnf

WORKDIR /opt/fieldora
COPY . /opt/fieldora
RUN python3.11 -m pip install --upgrade pip \
 && python3.11 -m pip install ".[server-postgresql]"
RUN groupadd --system fieldora \
 && useradd --system --gid fieldora --home-dir /var/lib/fieldora-storage --create-home fieldora \
 && mkdir -p /var/lib/fieldora-storage \
 && chown -R fieldora:fieldora /var/lib/fieldora-storage /opt/fieldora

USER fieldora
CMD ["fieldora-storage-service", "--help"]
