FROM sdp-docker-registry.kat.ac.za:5000/docker-base-build as build
MAINTAINER Mattieu de Villiers "mattieu@ska.ac.za"

# Enable Python 2 ve
ENV PATH="$PATH_PYTHON2" VIRTUAL_ENV="$VIRTUAL_ENV_PYTHON2"

# Install dependencies
COPY --chown=kat:kat requirements.txt /tmp/install/
RUN install-requirements.py -d ~/docker-base/base-requirements.txt -r /tmp/install/requirements.txt

# Install the package
COPY --chown=kat:kat . /tmp/install/katsdpdisp
WORKDIR /tmp/install/katsdpdisp
RUN python ./setup.py clean
RUN pip install --no-deps .
RUN pip check

#######################################################################

FROM sdp-docker-registry.kat.ac.za:5000/docker-base-runtime
MAINTAINER Mattieu de Villiers "mattieu@ska.ac.za"

COPY --from=build --chown=kat:kat /home/kat/ve /home/kat/ve
ENV PATH="$PATH_PYTHON2" VIRTUAL_ENV="$VIRTUAL_ENV_PYTHON2"
