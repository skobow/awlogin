export TARGET := awlogin
PKGSDIR := golibs
export GOPATH := $(CURDIR)/$(PKGSDIR):$(CURDIR)
export PATH := $(PATH):$(CURDIR)/$(PKGSDIR)/bin
SHELL := /bin/bash
MYBINDIR := $(HOME)/data/bin

default:
	go build -ldflags "-s -w" -o $(TARGET)
all:
	make clean-all
	mkdir $(PKGSDIR)
	go get -u github.com/aws/aws-sdk-go/...
	go get -u github.com/vaughan0/go-ini
	go get github.com/fatih/color
	go build -ldflags "-s -w" -o $(TARGET)
install:
	cp $(TARGET) $(MYBINDIR)/
clean:
	rm -rf $(TARGET)
clean-all:
	rm -rf $(TARGET) $(PKGSDIR)
