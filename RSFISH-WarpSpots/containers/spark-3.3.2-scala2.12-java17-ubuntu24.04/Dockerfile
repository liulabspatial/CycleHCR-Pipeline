FROM ubuntu:24.04

ARG SPARK_VERSION=3.3.2
ARG HADOOP_VERSION=3
ARG SCALA_VERSION=2.12

LABEL \
    org.opencontainers.image.title="Apache Spark" \
    org.opencontainers.image.description="Apache Spark is a unified analytics engine for large-scale data processing. This container combines the Spark runtime with additional scripts for simplified creation of Spark clusters." \
    org.opencontainers.image.authors="rokickik@janelia.hhmi.org" \
    org.opencontainers.image.licenses="Apache-2.0" \
    org.opencontainers.image.version=${SPARK_VERSION}

USER root

ARG spark_uid=185

RUN groupadd --system --gid=${spark_uid} spark \
 && useradd --system --uid=${spark_uid} --gid=spark spark

RUN set -ex; \
    apt-get update -y; \
    apt-get install -y \
        gnupg2 \
        wget curl tar tini libc6 libpam-modules \
        gnupg2 ca-certificates \
        krb5-user libnss3 procps net-tools hostname gosu \
        libnss-wrapper \
        python3 python3-pip \
        libzstd1 libzstd-dev;

# Install Java 17
RUN curl -O https://repos.azul.com/azul-repo.key; \
    gpg --dearmor < azul-repo.key > /usr/share/keyrings/azul.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/azul.gpg] https://repos.azul.com/zulu/deb stable main" | tee /etc/apt/sources.list.d/zulu.list; \
    apt update -y; \
    apt-get install -y zulu17-jdk;

ENV JAVA_HOME=/usr/lib/jvm/zulu17
ENV PATH=$JAVA_HOME/bin:$PATH

RUN mkdir /opt/spark; \
    mkdir /opt/spark/python; \
    mkdir /opt/spark/work-dir; \
    chmod g+w /opt/spark/work-dir; \
    touch /opt/spark/RELEASE; \
    chown -R spark:spark /opt/spark; \
    echo "auth required pam_wheel.so use_uid" >> /etc/pam.d/su; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /tmp

RUN mkdir sparkinstall; \
    cd sparkinstall; \
    wget https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz -O spark.tgz; \
    tar -xf spark.tgz --strip-components=1; \
    chown -R spark:spark .; \
    mv jars /opt/spark/; \
    mv RELEASE /opt/spark/; \
    mv bin /opt/spark/; \
    mv sbin /opt/spark/; \
    mv kubernetes/dockerfiles/spark/decom.sh /opt/; \
    mv python/pyspark /opt/spark/python/pyspark/; \
    mv python/lib /opt/spark/python/lib/; \
    mv R /opt/spark/; \
    chmod a+x /opt/decom.sh; \
    echo "${SPARK_VERSION}" > /opt/spark/VERSION; \
    cd ..; \
    rm -rf sparkinstall;

ENV SPARK_HOME=/opt/spark

# Install zstd-jni with setLongMax(int) support (version 1.5.5-6 or later required)
ARG ZSTD_JNI_VERSION=1.5.5-11
RUN rm -f /opt/spark/jars/zstd-jni-*.jar && \
    wget -P /opt/spark/jars/ https://repo1.maven.org/maven2/com/github/luben/zstd-jni/${ZSTD_JNI_VERSION}/zstd-jni-${ZSTD_JNI_VERSION}.jar && \
    chown spark:spark /opt/spark/jars/zstd-jni-${ZSTD_JNI_VERSION}.jar

WORKDIR /opt/spark//work-dir

ENV SPARK_WORK_DIR=/opt/spark//work-dir

# Add scripts for running pipelines
COPY ./scripts /opt/scripts
RUN chmod -R +x /opt/scripts
