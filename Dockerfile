from nvidia/cuda:11.5.1-devel-ubuntu20.04

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get clean
RUN apt-get update && apt-get install -y curl python3-pip git wget ffmpeg libsm6 libxext6
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.8 1


WORKDIR /content
RUN chmod ugoa+rwx /content
RUN chmod ugoa+rwx -R /usr/local/bin/

# # Install docker to run cog
RUN curl -fsSL https://get.docker.com | sh

# Install cog
RUN curl -o /usr/local/bin/cog -L https://github.com/replicate/cog/releases/latest/download/cog_`uname -s`_`uname -m`
RUN chmod +x /usr/local/bin/cog

# Install npm
ENV NODE_VERSION=16.13.0
RUN apt install -y curl
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
ENV NVM_DIR=/root/.nvm
RUN . "$NVM_DIR/nvm.sh" && nvm install ${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm use v${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm alias default v${NODE_VERSION}
ENV PATH="/root/.nvm/versions/node/v${NODE_VERSION}/bin/:${PATH}"
RUN node --version
RUN npm --version

RUN pip install --upgrade pip

ENV ipfs_root="/content/ipfs"
ENV worker_root="/content"
RUN mkdir -p $ipfs_root
RUN mkdir -p $ipfs_root/input
RUN mkdir -p $ipfs_root/output

RUN git clone https://github.com/pollinations/pollinations-ipfs.git
RUN cd /content/pollinations-ipfs && npm run install_backend

WORKDIR /app
COPY . /app
 
# CMD cd /content/pollinations/app && pollinate --execute "run_notebook.sh" -l $output_path/log -p $ipfs_root --ipns -n 123420 --debounce 200 > /content/cid
RUN pip install .

ENV AWS_REGION="us-east-1"
 
CMD ["python", "pollinator/main.py", "|&","utils/pipe_to_pollinator_logs_discord.sh"]