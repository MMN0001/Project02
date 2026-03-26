#include <stdio.h>
#include <stdlib.h>
#define N 100000

int arr[N];

int main() {
    for (int i = 0; i < N; i++) arr[i] = i;

    int sum = 0;
    for (int i = 0; i < N; i++) {
        int idx = rand() % N;
        sum += arr[idx];
    }

    printf("%d\n", sum);
    return 0;
}