#include <stdio.h>
#include <stdlib.h>

#define N 20000

struct Node {
    int val;
    struct Node* next;
};

int main() {
    struct Node* head = NULL;

    for (int i = 0; i < N; i++) {
        struct Node* node = malloc(sizeof(struct Node));
        node->val = i;
        node->next = head;
        head = node;
    }

    int sum = 0;
    struct Node* curr = head;
    while (curr) {
        sum += curr->val;
        curr = curr->next;
    }

    printf("%d\n", sum);
    return 0;
}