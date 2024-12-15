# Installation Guide: SingularityCE and Nextflow on Ubuntu

This guide provides step-by-step instructions for installing **SingularityCE** and **Nextflow** on Ubuntu. The instructions have been tested on Ubuntu 20.04 LTS and 22.04 LTS. Other versions may also work similarly. You will need `sudo` privileges.

---

## 1. Install SingularityCE

**Note:** SingularityCE (Community Edition) is the community-driven version of Singularity. It’s commonly installed from source.

### Prerequisites

1. Update and upgrade your system:
   ```bash
   sudo apt-get update
   sudo apt-get upgrade -y
   ```

2. Install required dependencies:

   ```
   sudo apt-get update && sudo apt-get install -y \
    build-essential \
    uuid-dev \
    libgpgme-dev \
    squashfs-tools \
    libseccomp-dev \
    wget \
    pkg-config \
    git \
    cryptsetup-bin \
    libglib2.0-dev \
    libfuse-dev \
    libfuse3-dev
   ```

3. Install Go (if you don’t have it already): SingularityCE requires Go version 1.20 or newer. Check your current Go version:

   ```
   go version
   ```

   If you don’t have Go or need a newer version, install it. For example:

   ```
   export VERSION=1.22.2 OS=linux ARCH=amd64 && \
    wget https://dl.google.com/go/go$VERSION.$OS-$ARCH.tar.gz && \
    sudo tar -C /usr/local -xzvf go$VERSION.$OS-$ARCH.tar.gz && \
    rm go$VERSION.$OS-$ARCH.tar.gz
   ```
   ```
   echo 'export GOPATH=${HOME}/go' >> ~/.bashrc && \
    echo 'export PATH=/usr/local/go/bin:${PATH}:${GOPATH}/bin' >> ~/.bashrc && \
    source ~/.bashrc
   ```

   Verify Go installation:
   ```
   go version
   ```

### Downloading and Building SingularityCE

1. Choose a SingularityCE version from the GitHub Releases. As an example:
    ```
    export VERSION=4.1.2 && \
    wget https://github.com/sylabs/singularity/releases/download/v${VERSION}/singularity-ce-${VERSION}.tar.gz && \
    tar -xzf singularity-ce-${VERSION}.tar.gz && \
    cd singularity-ce-${VERSION}
    ```

2. Build and install:
   ```
   ./mconfig && \
   make -C ./builddir && \
   sudo make -C ./builddir install
   ```

3. Verify the installation:
   ```
   singularity --version
   ```

   You should see something like:

   ```
   singularity version 4.1.2
   ```

### Basic Test

Try running a test container:
```
singularity exec library://alpine cat /etc/os-release
```
If successful, you should see Alpine’s OS release information.

---

## 2. Installing Nextflow

Nextflow requires Java (version 8 or newer). We’ll install OpenJDK 11 here.

### Prerequisites

1. Ensure Java is installed:
   ```
   sudo apt-get update
   sudo apt-get install -y openjdk-11-jre
   ```

2. Verify Java installation:
   ```
   java -version
   ```

   You should see something like:
   ```
    openjdk version "11.0.x" ...
   ```
### Installing Nextflow

1. Download and run the Nextflow installation script:
   
   ```
   curl -s http://get.nextflow.io | bash
   ```
   This creates the nextflow executable in your current directory.

2. Move nextflow into a system-wide location:
   ```
   sudo mv nextflow /usr/local/bin/
   sudo chmod +x /usr/local/bin/nextflow
   ```

3. Verify Nextflow installation:
   ```
   nextflow -version
   ```

### Quick Test

Run a simple Nextflow test pipeline:
```
nextflow run hello
```
If it works, you will see output similar to:
```
N E X T F L O W  ~  version x.x.x
Launching `nextflow-io/hello` [ ... ]

[warm up] executor > local
executor >  local (1)
[.../hello] process > sayHello [100%] 1 of 1 ✔
Hello world!
```