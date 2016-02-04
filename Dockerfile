FROM sdp-ingest5.kat.ac.za:5000/docker-base

MAINTAINER Mattieu de Villiers "mattieu@ska.ac.za"

# Install dependencies
COPY requirements.txt /tmp/install/
RUN install-requirements.py -d ~/docker-base/base-requirements.txt -r /tmp/install/requirements.txt

# Install the package
COPY . /tmp/install/katsdpdisp
WORKDIR /tmp/install/katsdpdisp
RUN python ./setup.py clean && pip install --no-index .
