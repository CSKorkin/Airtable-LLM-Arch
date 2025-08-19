SHELL := /bin/bash
.ONESHELL:
PY := python3.11
VENV := .venv311
PIP := $(VENV)/bin/pip

.PHONY: build clean deploy

build: clean
	$(PY) -m venv $(VENV)
	$(PIP) install --upgrade pip wheel
	mkdir -p build/create build/decompress dist
	$(PIP) install -r requirements.txt -t build/create
	$(PIP) install -r requirements.txt -t build/decompress
	cp -R app build/create/app
	cp -R app build/decompress/app
	touch build/create/app/__init__.py
	touch build/decompress/app/__init__.py
	cp lambdas/create/handler.py build/create/
	cp lambdas/decompress/handler.py build/decompress/
	( cd build/create && zip -r ../../dist/create_lambda.zip . )
	( cd build/decompress && zip -r ../../dist/decompress_lambda.zip . )

deploy: build
	terraform -chdir=terraform init
	terraform -chdir=terraform apply -auto-approve

clean:
	rm -rf dist build $(VENV)
