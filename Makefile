all: test

clean:
	rm -rf example.[ch] example.py *.o test __pycache__

test: test.o example.o example.h
	gcc -Wall -g test.o example.o -o test

example.c example.h: example.schema
	./generate.py example.schema

test.o: test.c example.h
	gcc -Wall -c test.c -o test.o

example.o: example.c example.h
	gcc -Wall -c example.c -o example.o


.PHONY: all clean
.DEFAULT_GOAL := all