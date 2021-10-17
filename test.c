#include <stdio.h>
#include <stdbool.h>
#include <string.h>
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
    size_t after_buffer_size;
    uint8_t *after_buf;

    printf("Testing Alpha\n");

    Alpha_get_alternative(a, &alt);
    if (alt != 42) {
        printf("This should be 42: %u\n", alt);
        return 1;
    }
    Alpha_serialize(a, &buf, &buffer_size);
    printf("Before set alt: ");
    xxd(buf, buffer_size);
    Alpha_t *alpha = Alpha_deserialize(buf, buffer_size);
    Alpha_print(alpha);
    Alpha_free(alpha);
    free(buf);

    Alpha_set_alternative(a, 3);
    Alpha_get_alternative(a, &alt);
    if (alt != 3) {
        printf("This should be 3: %u\n", alt);
        return 1;
    }
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
    uint32_t asteroids[3];
    for (size_t i = 0; i < 3; i++) {
        asteroids[i] = i;
    }
    Gamma_set_asteroid(g, asteroids, 3);
    const char *black_holes[] = {
        "Asdf",
        "Qwerty"
    };
    Gamma_set_black_hole(g, (char **)black_holes, 2);
    Color_e comet[] = {
        WHITE,
        BLACK,
        BLUE,
        ORANGE
    };
    Gamma_set_comet(g, comet, 4);
    bool deep_spaces[] = {
        true,
        true,
        false,
        true,
        false,
        false
    };
    Gamma_set_deep_space(g, deep_spaces, 6);
    Gamma_serialize(g, &buf, &buffer_size);
    printf("Gamma filled with a bunch of stuff\n");
    xxd(buf, buffer_size);
    Gamma_free(g);
    g = Gamma_deserialize(buf, buffer_size);
    Gamma_serialize(g, &after_buf, &after_buffer_size);
    if (memcmp(buf, after_buf, buffer_size) != 0) {
        printf("Gamma test failed\n");
        return 1;
    }
    Gamma_print(g);
    free(buf);
    free(after_buf);
    Delta_t *d = Delta_new();
    uint32_t artists[] = {
        3,
        12359056
    };
    const char *bakers[] = {
        "beep",
        "meep",
        "veep",
        "yeep"
    };
    Color_e chemists[] = {
        RED,
        RED,
        RED,
        RED,
        RED,
        RED
    };
    bool doctors[] = {
        true,
        true,
        true,
        true,
        true,
        true,
        true,
        true
    };

    Alpha_t *alpha_buf2[10];
    for (size_t i = 0; i < 10; i++) {
        alpha_buf2[i] = Alpha_copy(a);
    }
    Delta_set_engineer(d, alpha_buf2);
    for (size_t i = 0; i < 10; i++) {
        Alpha_free(alpha_buf2[i]);
    }
    Delta_set_artist(d, artists);
    Delta_set_baker(d, (char **)bakers);
    Delta_set_chemist(d, chemists);
    Delta_set_doctor(d, doctors);
    Delta_serialize(d, &buf, &buffer_size);
    printf("Delta filled with a bunch of stuff\n");
    xxd(buf, buffer_size);
    Delta_free(d);
    d = Delta_deserialize(buf, buffer_size);
    free(buf);
    Epsilon_t *e = Epsilon_new();
    Epsilon_set_altimeter(e, d);
    Zeta_t *z = Zeta_new();
    Zeta_set_austin_powers(z, e);
    Zeta_print(z);
    Zeta_serialize(z, &buf, &buffer_size);
    xxd(buf, buffer_size);
    Zeta_free(z);
    z = Zeta_deserialize(buf, buffer_size);
    Zeta_serialize(z, &after_buf, &after_buffer_size);
    if (memcmp(buf, after_buf, buffer_size) != 0) {
        printf("Error encountered in Zeta serialization and deserialization\n");
        return 1;
    }
    free(buf);
    free(after_buf);

    Zeta_print(z);

    Zeta_free(z);
    Epsilon_free(e);
    Delta_free(d);
    Alpha_free(a);
    Gamma_free(g);

    printf("All tests passed\n");
    return 0;
}
