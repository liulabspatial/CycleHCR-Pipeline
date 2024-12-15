# Create final image
FROM janeliascicomp/common-tools:1.0.2 as fiji-builder
WORKDIR /app/fiji
RUN curl -sL https://downloads.imagej.net/fiji/archive/20201104-1356/fiji-nojre.tar.gz | tar -xz -C /app/fiji
RUN chmod +x /app/fiji/Fiji.app/ImageJ-linux64 \
    && chown -R root:root /app/fiji \
    && ln -s /app/fiji/Fiji.app/ImageJ-linux64 /app/fiji/fiji

FROM janeliascicomp/zulu-jre:8u275b01 as zulu-builder

# Install an archived snapshot of Fiji
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        libxcb1 libxcb-shm0 libxcb-shape0 libxcb-xfixes0 libasound2 
COPY --from=fiji-builder /app/fiji /app/fiji


FROM condaforge/mambaforge

RUN mamba create -n myenv -c conda-forge python=3.8 tqdm numpy=1.20 scikit-image=0.18 \
        zarr=2.7 dask=2021.4 dask-image=0.5.0 -y \
    && mamba run -n myenv pip install xarray-multiscale fibsem-tools \
    && mamba clean --tarballs -y \
    && mkdir -p /opt/conda/envs/myenv/etc/conda/activate.d \
    # It's necessary to set TMPDIR for running with Singularity, because /opt/conda will be read-only
    && echo "export TMPDIR=/tmp" > /opt/conda/envs/myenv/etc/conda/activate.d/env_vars.sh

# ps is needed by nextflow to collect task metrics
RUN apt-get install -y procps

COPY scripts /app

# Define maintainer
LABEL maintainer="Janelia Scientific Computing"

# Add fiji to the PATH
ENV PATH $PATH:/app/fiji/Fiji.app

# JDK paths
ENV JAVA_HOME=/usr/lib/jvm/zulu-8-jre-amd64
ENV PATH="$JAVA_HOME/bin:${PATH}"

# Install an archived snapshot of Fiji
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        libxcb1 libxcb-shm0 libxcb-shape0 libxcb-xfixes0 libasound2 
COPY --from=zulu-builder /app/fiji /app/fiji
COPY --from=zulu-builder /usr/lib/jvm/zulu-8-jre-amd64 /usr/lib/jvm/zulu-8-jre-amd64

RUN /app/fiji/Fiji.app/ImageJ-linux64 --headless --console --update add-update-site BigStitcher https://sites.imagej.net/BigStitcher/
RUN /app/fiji/Fiji.app/ImageJ-linux64 --headless --console --update update

#ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "myenv", "python", "run.py"]

RUN echo "#!/bin/bash" >> /entrypoint.sh \
    && echo "source /opt/conda/etc/profile.d/conda.sh" >> /entrypoint.sh \
    && echo "SCRIPT_NAME=\$1; shift" >> /entrypoint.sh \
    && echo "conda activate myenv" >> /entrypoint.sh \
    && echo 'python /app/${SCRIPT_NAME}.py "$@"' >> /entrypoint.sh \
    && chmod +x /entrypoint.sh
#ENTRYPOINT [ "/entrypoint.sh" ]
