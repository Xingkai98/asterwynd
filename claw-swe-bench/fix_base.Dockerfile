FROM sweb.base.py.x86_64:latest
RUN /opt/miniconda3/bin/conda install -n base conda-libmamba-solver -y && \
    /opt/miniconda3/bin/conda config --set solver libmamba
