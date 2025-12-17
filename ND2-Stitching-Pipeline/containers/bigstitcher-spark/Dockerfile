
ARG BIGSTITCHER_SPARK_GIT_TAG=main

# Temporary container for building cleanly
FROM janeliascicomp/builder:1.3.0 as downloader
ARG BIGSTITCHER_SPARK_GIT_TAG

# Checkout and build the code
WORKDIR /tmp/app

RUN git clone --branch main --depth 1 https://github.com/takashi310/BigStitcher-Spark.git . \
    && /usr/local/bin/buildinfo.sh \
    && xq -r '.project.artifactId+"-"+.project.version+".jar"' pom.xml > filename

RUN curl -sL https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.6.3/apache-maven-3.6.3-bin.tar.gz | tar -xz -C /tmp/app
RUN chmod +x /tmp/app/apache-maven-3.6.3/bin/mvn \
    && chown -R root:root /tmp/app/apache-maven-3.6.3 \
    && ln -s /tmp/app/apache-maven-3.6.3/bin/mvn /tmp/app/apache-maven-3.6.3/mvn

FROM janeliascicomp/zulu-fx:8 as builder
ARG BIGSTITCHER_SPARK_GIT_TAG

WORKDIR /tmp/app
COPY --from=downloader /tmp/app /tmp/app
COPY --from=downloader /buildinfo /buildinfo
ENV M2_HOME=/tmp/app/apache-maven-3.6.3
ENV MAVEN_HOME=/tmp/app/apache-maven-3.6.3
ENV PATH=${M2_HOME}/bin:${PATH}
RUN apt-get update && apt install -y libblosc1 libblosc-dev wget unzip && apt-get clean && rm -rf /var/lib/apt/lists/* /var/tmp/* 
ENV LD_LIBRARY_PATH=/usr/lib:${LD_LIBRARY_PATH}
RUN mvn clean package -P fatjar

RUN mkdir -p /tmp/scripts \
    && wget -qO /tmp/containers.zip https://github.com/BioContainers/containers/archive/master.zip \
    && unzip /tmp/containers.zip -d /tmp \
    && cp -r /tmp/containers-master/spark/3.1.3/scripts/* /tmp/scripts/ \
    && rm -rf /tmp/containers-master /tmp/containers.zip

# Find the built jar, based on the version in the pom file
RUN mv /tmp/app/target/`cat filename` app.jar

RUN echo "$BIGSTITCHER_SPARK_GIT_TAG" > /tmp/app/VERSION



# Create final image
FROM ubuntu:20.04

USER 0

# eliminate input warnings from debconf
ARG DEBIAN_FRONTEND=noninteractive

# set timezone for GTK
ENV TZ=US/Eastern
# JDK paths
ENV JAVA_HOME=/usr/lib/jvm/zulu-8-fx-amd64
ENV SPARK_HOME=/opt/spark
ENV PATH=$PATH:$JAVA_HOME/bin:$SPARK_HOME/bin:$SPARK_HOME/sbin

RUN apt-get update \
    # UTF-8 by default
    && apt-get install --no-install-recommends -y locales curl \
    && echo "LC_ALL=en_US.UTF-8" >> /etc/environment \
    && echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen \
    && echo "LANG=en_US.UTF-8" > /etc/locale.conf \
    && locale-gen en_US.UTF-8 \
    # Dependencies for X11 rendering
    && apt-get install --no-install-recommends -y libxext6 libxrender1 libxtst6 libxi6 \
    # Because https://support.azul.com/hc/en-us/articles/360034030692-Using-Fonts-with-OpenJDK-Zulu
    && apt-get install --no-install-recommends -y fonts-dejavu fontconfig \
    # GTK required by JavaFX
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && apt-get install --no-install-recommends -y gtk3.0 \
    # Install ZuluFX
    && mkdir -p /usr/lib/jvm/zulu-8-fx-amd64 \
	&& curl -sL https://cdn.azul.com/zulu/bin/zulu8.48.0.53-ca-fx-jdk8.0.265-linux_x64.tar.gz \
    | tar -xz --strip-components=1 -C /usr/lib/jvm/zulu-8-fx-amd64 \
    # Clean up this layer
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/* 



ARG spark_uid=185

RUN groupadd --system --gid=${spark_uid} spark && \
    useradd --system --uid=${spark_uid} --gid=spark spark

RUN set -ex; \
    apt-get update; \
    apt-get install -y gnupg2 wget bash tini libc6 libpam-modules krb5-user libnss3 procps net-tools gosu libnss-wrapper; \
    mkdir -p /opt/spark; \
    mkdir /opt/spark/python; \
    mkdir -p /opt/spark/examples; \
    mkdir -p /opt/spark/work-dir; \
    chmod g+w /opt/spark/work-dir; \
    touch /opt/spark/RELEASE; \
    chown -R spark:spark /opt/spark; \
    echo "auth required pam_wheel.so use_uid" >> /etc/pam.d/su; \
    rm -rf /var/lib/apt/lists/*

# Install Apache Spark
# https://downloads.apache.org/spark/KEYS
ENV SPARK_TGZ_URL=https://archive.apache.org/dist/spark/spark-3.5.4/spark-3.5.4-bin-hadoop3.tgz \
    SPARK_TGZ_ASC_URL=https://archive.apache.org/dist/spark/spark-3.5.4/spark-3.5.4-bin-hadoop3.tgz.asc \
    GPG_KEY=19F745C40A0E550420BB2C522541488DA93FE4B4

RUN set -ex; \
    export SPARK_TMP="$(mktemp -d)"; \
    cd $SPARK_TMP; \
    wget -nv -O spark.tgz "$SPARK_TGZ_URL"; \
    wget -nv -O spark.tgz.asc "$SPARK_TGZ_ASC_URL"; \
    export GNUPGHOME="$(mktemp -d)"; \
    gpg --batch --keyserver hkps://keys.openpgp.org --recv-key "$GPG_KEY" || \
    gpg --batch --keyserver hkps://keyserver.ubuntu.com --recv-keys "$GPG_KEY"; \
    gpg --batch --verify spark.tgz.asc spark.tgz; \
    gpgconf --kill all; \
    rm -rf "$GNUPGHOME" spark.tgz.asc; \
    \
    tar -xf spark.tgz --strip-components=1; \
    chown -R spark:spark .; \
    mv jars /opt/spark/; \
    mv RELEASE /opt/spark/; \
    mv bin /opt/spark/; \
    mv sbin /opt/spark/; \
    mv kubernetes/dockerfiles/spark/decom.sh /opt/; \
    mv examples /opt/spark/; \
    ln -s "$(basename /opt/spark/examples/jars/spark-examples_*.jar)" /opt/spark/examples/jars/spark-examples.jar; \
    mv kubernetes/tests /opt/spark/; \
    mv data /opt/spark/; \
    mv python/pyspark /opt/spark/python/pyspark/; \
    mv python/lib /opt/spark/python/lib/; \
    mv R /opt/spark/; \
    chmod a+x /opt/decom.sh; \
    cd ..; \
    rm -rf "$SPARK_TMP";

ENV SPARK_HOME /opt/spark

WORKDIR /opt/spark/work-dir
RUN chmod g+w /opt/spark/work-dir
RUN chmod a+x /opt/decom.sh


ARG BIGSTITCHER_SPARK_GIT_TAG

RUN apt-get update && apt install -y procps g++ libblosc1 libblosc-dev && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* 

LABEL software="bigstitcher-spark" \
    base_image="apache/spark" \
    container="bigstitcher-spark" \
    about.summary="Running compute-intense parts of BigStitcher distributed" \
    about.home="https://github.com/JaneliaSciComp/BigStitcher-Spark" \
    software.version=${BIGSTITCHER_SPARK_GIT_TAG} \
    upstream.version=${BIGSTITCHER_SPARK_GIT_TAG} \
    version="1" \
    about.license="BSD-2-Clause" \
    about.license_file="/app/LICENSE.txt" \
    extra.binaries="/opt/spark/bin" \
    about.tags="implemented-in::java, interface::commandline, role::program" \
    bioimagetools.image.authors="kawaset@janelia.hhmi.org"

WORKDIR /app
COPY --from=builder /tmp/app/LICENSE /app/LICENSE
COPY --from=builder /tmp/app/VERSION /app
COPY --from=builder /tmp/app/app.jar /app
COPY --from=builder /buildinfo /app
COPY --from=builder /tmp/scripts /opt/scripts

RUN chmod -R +x /opt/scripts
