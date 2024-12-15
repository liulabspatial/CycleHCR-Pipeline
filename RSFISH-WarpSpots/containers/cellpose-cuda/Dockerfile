FROM oraclelinux:8

ENV DOWNLOAD_CONDA_URL=https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh

ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=all

# ps is needed by nextflow to collect task metrics
#RUN apt-get install -y procps

RUN dnf group install -y "Development Tools" && \
    dnf install -y \
        git wget \
        ocl-icd

RUN mkdir /tmp-install && \
    cd /tmp-install && \
    wget ${DOWNLOAD_CONDA_URL} -O miniconda-install.sh && \
    bash miniconda-install.sh -b -p /miniconda && \
    rm miniconda-install.sh && \
    rm -rf /tmp-install
    
ENV PATH=/miniconda/bin:${PATH}

RUN conda config --set always_yes yes --set changeps1 no && \
    conda update -q conda

RUN conda install -n base -c conda-forge python=3.10.12 tqdm numpy=1.24.3 scikit-image=0.22.0 \
        zarr=2.13.3 dask=2023.11.0 dask-image tifffile nd2 -y \
    && conda run -n base pip install gputools xarray-multiscale fibsem-tools cellpose==2.2.3 \
    && conda clean --tarballs -y \
    && mkdir -p /opt/conda/envs/myenv/etc/conda/activate.d \
    # It's necessary to set TMPDIR for running with Singularity, because /opt/conda will be read-only
    && echo "export TMPDIR=/tmp" > /opt/conda/envs/myenv/etc/conda/activate.d/env_vars.sh

COPY scripts /app

#ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "myenv", "python", "run.py"]

RUN echo "#!/bin/bash" >> /entrypoint.sh \
    && echo "SCRIPT_NAME=\$1; shift" >> /entrypoint.sh \
    && echo 'python /app/${SCRIPT_NAME}.py "$@"' >> /entrypoint.sh \
    && chmod +x /entrypoint.sh
#ENTRYPOINT [ "/entrypoint.sh" ]