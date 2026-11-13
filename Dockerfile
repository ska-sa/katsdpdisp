ARG KATSDPDOCKERBASE_REGISTRY=harbor.sdp.kat.ac.za/dpp

FROM $KATSDPDOCKERBASE_REGISTRY/docker-base-build AS build

# uv is installed in ~/.local/bin in the base image
# Activate the base image virtualenv and make uv available
ENV PATH="/home/kat/.local/bin:$PATH_PYTHON3" VIRTUAL_ENV="$VIRTUAL_ENV_PYTHON3"

# Install dependencies
COPY --chown=kat:kat base-requirements.txt /tmp/install/
COPY --chown=kat:kat requirements.txt /tmp/install/

RUN uv pip compile /tmp/install/requirements.txt \
    -o /tmp/install/requirements.lock && \
    uv pip install --no-deps -r /tmp/install/requirements.lock&&\
    uv pip check

# Install the package
COPY --chown=kat:kat . /tmp/install/katsdpdisp

RUN cd /tmp/install/katsdpdisp && \
    python3 ./setup.py clean   && \
    uv pip install --no-deps . && \
    uv pip check
#######################################################################

FROM $KATSDPDOCKERBASE_REGISTRY/docker-base-runtime
LABEL maintainer="sdpdev+katsdpdisp@ska.ac.za"

COPY --from=build --chown=kat:kat /home/kat/ve3 /home/kat/ve3
ENV PATH="$PATH_PYTHON3" VIRTUAL_ENV="$VIRTUAL_ENV_PYTHON3"
