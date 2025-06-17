#!/bin/bash
source "$HOME/miniforge3/bin/activate" stream-mod && \
cd "$HOME/stream-mod/front" && \
mod_wsgi-express start-server application.wsgi --port 7011 \
	--server-root "$HOME/stream-mod/apache-app-front" \
	--access-log --log-to-terminal \
	2>&1 | /usr/bin/cronolog "$HOME/stream-mod/apache-app-front/logs/apache.%Y-%m-%d.log"