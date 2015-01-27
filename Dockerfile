FROM ubuntu:14.04

MAINTAINER Mattieu de Villiers "mattieu@ska.ac.za"

# Set up access to github private repositories
COPY conf/id_rsa /root/.ssh/
RUN echo "Host *\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config
RUN chmod -R go-rwx ~/.ssh

# Work in a tmpfs, to avoid bloating the image. Note that the contents
# disappear between RUN steps, so each step must completely use the files
# it needs.
WORKDIR /dev
ENV TMPDIR /dev

# Install system packages. Python packages are mostly installed here, but
# certain packages are handled by pip:
# - Not available in Ubuntu 14.04 (universe): pyephem, scikits.fitting, pycuda, katcp, ansicolors
# - Ubuntu 14.04 version is too old: six
RUN apt-get -y update && apt-get -y install \
    build-essential software-properties-common wget git-core \
    python python-dev python-pip \
    python-appdirs \
    python-blinker \
    python-decorator \
    python-h5py \
    python-iniparse \
    python-mako \
    python-markupsafe \
    python-mock \
    python-nose \
    python-numpy \
    python-ply \
    python-py \
    python-pytools \
    python-scipy \
    python-twisted \
    python-unittest2 \
    gfortran libatlas-base-dev libblas-dev libexpat1-dev \
    ipython \
    python-matplotlib

# Install Python dependencies. Versions are explicitly listed and pinned, so
# that the docker image is reproducible. There were all up-to-date versions
# at the time of writing i.e. there are no currently known reasons not to
# update to newer versions.
RUN pip install --no-deps \
    ansicolors==1.0.2 \
    katcp==0.5.5 \
    pyephem==3.7.5.3 \
    scikits.fitting==0.5.1 \
    mplh5canvas==0.7 \
    guppy==0.1.10 \
    ProxyTypes==0.9 \
    mod_pywebsocket==0.7.9
COPY requirements.txt /tmp/install/requirements.txt
# Keep only dependent git repositories; everything else is installed explicitly
# by this Dockerfile.
RUN sed -n '/^git/p' /tmp/install/requirements.txt > /tmp/install/requirements-git.txt && \
    pip install --no-deps -r /tmp/install/requirements-git.txt

# Install the current package
COPY . /tmp/install/katsdpdisp
WORKDIR /tmp/install/katsdpdisp
RUN python ./setup.py install

# Run signal displays as a non-root user
RUN adduser --system kat
WORKDIR /home/kat
ENV TMPDIR /tmp
USER kat
