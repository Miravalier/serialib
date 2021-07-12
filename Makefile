test: test.o example.o example.h
	gcc -Wall -g test.o example.o -o test

example.c example.h: example.schema
	./generate.py example.schema

test.o: test.c
	gcc -Wall -c test.c -o test.o

example.o: example.c example.h
	gcc -Wall -c example.c -o example.o