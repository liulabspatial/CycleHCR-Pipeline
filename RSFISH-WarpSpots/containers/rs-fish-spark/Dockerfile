ARG SPARK_VERSION=3.3.2-scala2.12-java17-ubuntu24.04
ARG RS_FISH_REPO=https://github.com/cgoina/RS-FISH-Spark.git
ARG RS_FISH_BRANCH=ome
ARG RS_FISH_SPARK_GIT_HASH=e1a45d0

# Staged build using builder container with java8
# because Bigstitcher still needs java8 to build
FROM azul/zulu-openjdk:8-latest AS builder
ARG RS_FISH_REPO
ARG RS_FISH_BRANCH
ARG RS_FISH_SPARK_GIT_HASH

RUN apt-get update -y; \
    apt-get install -y git curl maven; \
    curl -sSL https://bit.ly/install-xq | bash;

# Checkout and build the code
WORKDIR /tmp/app
RUN git clone --branch ${RS_FISH_BRANCH} ${RS_FISH_REPO} . \
    && git reset --hard ${RS_FISH_SPARK_GIT_HASH} \
    && perl -i -pe 's|(<artifactId>n5-universe</artifactId>\s*)<version>[^<]+</version>|$1<version>2.3.0</version>|s' pom.xml \
    && perl -i -pe 's|<artifactId>n5</artifactId>|<artifactId>n5</artifactId>\n            <version>3.3.1</version>|' pom.xml \
    && perl -i -pe 's|<artifactId>n5-zarr</artifactId>|<artifactId>n5-zarr</artifactId>\n            <version>1.3.5</version>|' pom.xml \
    && perl -i -pe 's|<artifactId>n5-aws-s3</artifactId>|<artifactId>n5-aws-s3</artifactId>\n            <version>4.2.1</version>|' pom.xml \
    && perl -i -pe 'BEGIN{undef $/;} s|</dependencies>|        <dependency>\n            <groupId>commons-io</groupId>\n            <artifactId>commons-io</artifactId>\n            <version>2.21.0</version>\n        </dependency>\n    </dependencies>|s' pom.xml \
    && perl -i -pe 'BEGIN{undef $/;} s|(<pattern>org.apache.commons.compress</pattern>\s*<shadedPattern>org.janelia.saalfeldlab.org.apache.commons.compress</shadedPattern>\s*</relocation>)|$1\n                        <!-- Protect newer commons-io version from the old one preloaded by spark -->\n                        <relocation>\n                            <pattern>org.apache.commons.io</pattern>\n                            <shadedPattern>org.janelia.saalfeldlab.org.apache.commons.io</shadedPattern>\n                        </relocation>|s' pom.xml \
    && perl -i -pe 'BEGIN{undef $/;} s|(<artifactSet>\s*<excludes>)|$1\n                            <exclude>com.github.luben:zstd-jni</exclude>|s' pom.xml \
    && echo "=== Verifying pom.xml modifications ===" \
    && grep -A 3 "n5-universe" pom.xml \
    && grep -A 1 "n5</artifactId>" pom.xml \
    && grep -A 1 "n5-zarr" pom.xml \
    && grep -A 3 "commons-io" pom.xml \
    && echo "=== Checking relocations ===" \
    && grep -A 2 "org.apache.commons.io" pom.xml || echo "Relocation not found - checking full relocations section" \
    && grep -A 20 "<relocations>" pom.xml \
    && echo "=== Checking zstd-jni exclusion ===" \
    && grep -A 5 "<artifactSet>" pom.xml \
    && echo "=== Starting Maven build ===" \
    && mvn package -DskipTests

# Find the built jar, based on the version in the pom file
RUN xq -x '/project/artifactId' pom.xml > target-name \
 && xq -x '/project/version' pom.xml > target-version \
 && echo "Rename target/$(cat target-name)-$(cat target-version)-with-dependencies.jar" \
 && mv target/$(cat target-name)-$(cat target-version)-with-dependencies.jar app.jar

RUN echo "${RS_FISH_BRANCH}:${RS_FISH_SPARK_GIT_HASH}" > /tmp/app/VERSION

FROM ghcr.io/janeliascicomp/spark:${SPARK_VERSION}
ARG RS_FISH_SPARK_GIT_HASH

LABEL \
    org.opencontainers.image.title="RS-FISH Spark" \
    org.opencontainers.image.description="Spark version of RS-FISH" \
    org.opencontainers.image.authors="rokickik@janelia.hhmi.org,preibischs@janelia.hhmi.org,goinac@janelia.hhmi.org,kawaset@janelia.hhmi.org" \
    org.opencontainers.image.licenses="GPL-2.0" \
    org.opencontainers.image.version=${RS_FISH_SPARK_GIT_HASH}

USER root

RUN apt update -y; \
    apt-get install -y \
        libblosc1 libblosc-dev \
        libzstd1 libzstd-dev libhdf5-dev;

# Download and install newer commons-io to replace the old version in Spark
RUN echo "Downloading commons-io 2.15.1..." \
    && curl -L https://repo1.maven.org/maven2/commons-io/commons-io/2.15.1/commons-io-2.15.1.jar \
    -o /tmp/commons-io-2.15.1.jar \
    && echo "Removing old commons-io versions from Spark jars..." \
    && find /opt/spark/jars -name "commons-io-*.jar" -delete || true \
    && echo "Installing new commons-io..." \
    && mv /tmp/commons-io-2.15.1.jar /opt/spark/jars/ \
    && echo "commons-io 2.15.1 installed successfully"

# Download and install newer zstd-jni to fix setLongMax(int) NoSuchMethodError
RUN echo "Downloading zstd-jni 1.5.5-11..." \
    && curl -L https://repo1.maven.org/maven2/com/github/luben/zstd-jni/1.5.5-11/zstd-jni-1.5.5-11.jar \
    -o /tmp/zstd-jni-1.5.5-11.jar \
    && echo "Removing old zstd-jni versions from Spark jars..." \
    && find /opt/spark/jars -name "zstd-jni-*.jar" -delete || true \
    && echo "Installing new zstd-jni..." \
    && mv /tmp/zstd-jni-1.5.5-11.jar /opt/spark/jars/ \
    && echo "zstd-jni 1.5.5-11 installed successfully"

WORKDIR /app
COPY --from=builder /tmp/app/LICENSE.txt /app/LICENSE
COPY --from=builder /tmp/app/VERSION /app
COPY --from=builder /tmp/app/app.jar /app/app.jar