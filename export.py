#!/usr/bin/env python3

import getpass
import endoapi.endomondo


def main():
    email = input("Email: ")
    password = getpass.getpass()
    maximum_workouts = 10
    endomondo = endoapi.endomondo.Endomondo(email, password)

    workouts = endomondo.get_workouts(maximum_workouts)

    for workout in workouts:
        print(workout)


if __name__ == "__main__":
    main()
