SHELL := /bin/sh
IMAGE ?= ghcr.io/liofal/proxmox-cert-sync:dev

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  build-image    Build the container image"

.PHONY: build-image
build-image:
	@docker build -t $(IMAGE) .
