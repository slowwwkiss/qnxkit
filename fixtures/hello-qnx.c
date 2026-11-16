/*
 * hello-qnx.c — minimal QNX Neutrino message-passing demo.
 *
 * Server mode (default): creates a channel, attaches the name
 * "hello_qnx", and replies to every message with a greeting.
 * Client mode ("hello-qnx client"): opens the name and sends one
 * message with MsgSend(), then prints the reply.
 *
 * Build for QNX 8.0 (needs QNX SDP 8.0):
 *   qcc -Vgcc_ntoaarch64le -o hello-qnx hello-qnx.c
 *   qcc -Vgcc_ntox86_64    -o hello-qnx hello-qnx.c
 *
 * The QNX-native APIs used here — ChannelCreate, name_attach,
 * MsgReceive, MsgReply, name_open, MsgSend — are exactly what
 * `qnxkit analyze` counts as QNX targeting evidence.
 */

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/neutrino.h>
#include <sys/netmgr.h>

#define SERVICE_NAME "hello_qnx"

static int run_server(void)
{
    int chid = ChannelCreate(0);
    if (chid == -1) {
        perror("ChannelCreate");
        return EXIT_FAILURE;
    }
    if (name_attach(NULL, SERVICE_NAME, 0) == NULL) {
        perror("name_attach");
        return EXIT_FAILURE;
    }
    printf("hello-qnx: listening on /dev/name/local/%s\n", SERVICE_NAME);
    for (;;) {
        char msg[256];
        int rcvid = MsgReceive(chid, msg, sizeof(msg), NULL);
        if (rcvid == -1)
            continue; /* interrupted; keep listening */
        if (rcvid == 0)
            continue; /* pulse, not a message */
        msg[sizeof(msg) - 1] = '\0';
        printf("hello-qnx: got %d bytes: %s\n", (int)strlen(msg), msg);
        {
            const char *reply = "hello from QNX 8.0";
            MsgReply(rcvid, EOK, reply, strlen(reply));
        }
    }
    return EXIT_SUCCESS;
}

static int run_client(void)
{
    int coid = name_open(SERVICE_NAME, 0);
    if (coid == -1) {
        perror("name_open");
        return EXIT_FAILURE;
    }
    {
        char reply[256];
        const char *request = "ping";
        int status = MsgSend(coid, request, strlen(request) + 1,
                             reply, sizeof(reply));
        if (status == -1) {
            perror("MsgSend");
            return EXIT_FAILURE;
        }
        reply[sizeof(reply) - 1] = '\0';
        printf("hello-qnx: server replied: %s\n", reply);
    }
    return EXIT_SUCCESS;
}

int main(int argc, char **argv)
{
    if (argc > 1 && strcmp(argv[1], "client") == 0)
        return run_client();
    return run_server();
}
