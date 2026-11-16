/*
 * linux-only.c — a Linux daemon snippet that does NOT port to QNX.
 *
 * Deliberately uses Linux-only facilities so `qnxkit analyze` has
 * something to find: epoll, inotify, eventfd, timerfd, memfd,
 * io_uring, prctl, clone, sched_setaffinity, __GLIBC__, /proc/self
 * paths and raw syscalls. The comment below mentions epoll and the
 * string literal mentions epoll_create — neither must raise a
 * finding, because comments and strings are stripped first.
 *
 * NOTE: this file mentions epoll in prose only to test the stripper.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sched.h>
#include <sys/epoll.h>
#include <sys/inotify.h>
#include <sys/eventfd.h>
#include <sys/timerfd.h>
#include <sys/memfd.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <liburing.h>
#include <linux/limits.h>

static int child_main(void *arg)
{
    (void)arg;
    return 0;
}

int main(void)
{
    const char *label = "epoll_create is Linux-only";
    (void)label;

    int efd = epoll_create1(0);
    struct epoll_event ev;
    memset(&ev, 0, sizeof(ev));
    epoll_ctl(efd, EPOLL_CTL_ADD, 0, &ev);
    epoll_wait(efd, &ev, 1, -1);

    int ifd = inotify_init1(IN_NONBLOCK);
    inotify_add_watch(ifd, "/etc", IN_MODIFY);
    inotify_rm_watch(ifd, 1);

    int evfd = eventfd(0, 0);
    (void)evfd;

    int tfd = timerfd_create(CLOCK_MONOTONIC, 0);
    (void)tfd;

    int mfd = memfd_create("buf", 0);
    (void)mfd;

    struct io_uring ring;
    io_uring_queue_init(8, &ring, 0);
    io_uring_queue_exit(&ring);

    prctl(PR_SET_NAME, "worker", 0, 0, 0);

    {
        char stack[8192];
        clone(child_main, stack + sizeof(stack), CLONE_VM, NULL);
    }

    {
        cpu_set_t set;
        CPU_ZERO(&set);
        CPU_SET(0, &set);
        sched_setaffinity(0, sizeof(set), &set);
    }

#ifdef __GLIBC__
    printf("glibc %d\n", __GLIBC__);
#endif

    {
        char path[256];
        snprintf(path, sizeof(path), "/proc/self/exe");
        printf("self: %s\n", path);
    }

    syscall(SYS_getpid);
    return 0;
}
