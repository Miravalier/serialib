#include <stdio.h>
#include "example.h"

void xxd(void *bytes, size_t size) {
    printf("'");
    for (size_t i = 0; i < size; i++) {
        
        if (i == size - 1) {
            printf("%02x", ((uint8_t*)bytes)[i]);
        }
        else {
            printf("%02x ", ((uint8_t*)bytes)[i]);
        }
    }
    printf("'\n");
}

int main() {
    Alpha_t *a = Alpha_new();
    uint32_t alt;
    size_t buffer_size;
    uint8_t *buf;
    printf("Testing Alpha\n");
    Alpha_get_alternative(a, &alt);
    printf("This should be 42: %u\n", alt);
    Alpha_serialize(a, &buf, &buffer_size);
    printf("Before set alt: ");
    xxd(buf, buffer_size);
    free(buf);
    Alpha_set_alternative(a, 3);
    Alpha_get_alternative(a, &alt);
    printf("This should be 3: %u\n", alt);
    Alpha_serialize(a, &buf, &buffer_size);
    printf("After set alt: ");
    xxd(buf, buffer_size);
    free(buf);
    Alpha_set_alternative(a, 17);
    Alpha_set_blues(a, "smiley face 1 1 1 2 2 3");
    Alpha_set_country(a, ORANGE);
    Alpha_set_disco(a, false);
    Alpha_serialize(a, &buf, &buffer_size);
    printf("After setting every field:\n");
    xxd(buf, buffer_size);
    free(buf);
    printf("Alpha testing done! Moving on to Gamma\n");

    Gamma_t *g = Gamma_new();
    Alpha_t *alpha_buf[4];
    for (size_t i = 0; i < 4; i++) {
        alpha_buf[i] = Alpha_copy(a);
    }
    Gamma_set_earth(g, alpha_buf, 4);
    for (size_t i = 0; i < 4; i++) {
        Alpha_free(alpha_buf[i]);
    }
    Gamma_serialize(g, &buf, &buffer_size);
    printf("Gamma filled with 4 alphas\n");
    xxd(buf, buffer_size);
    free(buf);
    Alpha_free(a);
    Gamma_free(g);
}