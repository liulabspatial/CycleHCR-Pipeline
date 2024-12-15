ARG SPARK_VERSION=3.1.3
ARG BIGSTITCHER_SPARK_GIT_TAG=main

# Temporary container for building cleanly
FROM janeliascicomp/builder:1.3.0 as downloader
ARG BIGSTITCHER_SPARK_GIT_TAG

# Checkout and build the code
WORKDIR /tmp/app
# TODO: currently this points to a fork which adds a minor feature. It can be switched back to https://github.com/saalfeldlab/stitching-spark after the PR is merged.
#RUN git clone --branch ${BIGSTITCHER_SPARK_GIT_TAG} --depth 1 https://github.com/JaneliaSciComp/BigStitcher-Spark.git . \
#    && /usr/local/bin/buildinfo.sh \
#    && xq -r '.project.artifactId+"-"+.project.version+".jar"' pom.xml > filename
#RUN git init \
#    && git remote add origin https://github.com/takashi310/BigStitcher-Spark.git \
#    && git fetch --depth 1 origin 17f52a6f1430c9a98e965c66465172560134a872 \
#    && git reset --hard FETCH_HEAD \
#    && /usr/local/bin/buildinfo.sh \
#    && xq -r '.project.artifactId+"-"+.project.version+".jar"' pom.xml > filename

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
RUN apt-get update && apt install -y libblosc1 libblosc-dev && apt-get clean && rm -rf /var/lib/apt/lists/* /var/tmp/* 
ENV LD_LIBRARY_PATH=/usr/lib:${LD_LIBRARY_PATH}
RUN mvn clean package -P fatjar

# Find the built jar, based on the version in the pom file
RUN mv /tmp/app/target/`cat filename` app.jar

RUN echo "$BIGSTITCHER_SPARK_GIT_TAG" > /tmp/app/VERSION

# Create final image
FROM multifish/spark:3.0.1-hadoop3.2
ARG BIGSTITCHER_SPARK_GIT_TAG

# RUN apt-get update && apt install -y procps g++ libblosc1 libblosc-dev && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* 
RUN yum update -y && yum install -y procps gcc-c++ cmake git && yum clean all && rm -rf /tmp/* /var/tmp/* 

WORKDIR /tmp/lib

RUN git clone --branch main --depth 1 https://github.com/Blosc/c-blosc.git
WORKDIR /tmp/lib/c-blosc/build
RUN cmake -S /tmp/lib/c-blosc -B /tmp/lib/c-blosc/build \
    && make \
    && make install


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