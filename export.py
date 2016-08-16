#!/usr/bin/env python

from lib.endomondo import Endomondo
import getpass

def create_tcx_file(workout):
    directory_name = 'export'
    activity = workout.get_activity()
    print(str(activity))

#    name = create_filename(workout)
#    create_directory(directory_name)
#    filename = os.path.join(directory_name, name)
#    print("writing %s, %s, %s trackpoints".format(filename, activity.sport, len(activity.trackpoints)))
#
#    writer = tcx.Writer()
#    tcxfile = writer.write(activity)
#    if tcxfile:
#        with open(filename, 'w') as f:
#            f.write(tcxfile)


def main():
    email = input("email: ")
    password = getpass.getpass()
    maximum_workouts = input("maximum number of workouts (press Enter to ignore)")
    endomondo = Endomondo(email, password)

    workouts = endomondo.get_workouts(maximum_workouts)
    print("fetched latest", len(workouts), "workouts")
    for workout in workouts:
        create_tcx_file(workout)


if __name__ == "__main__":
    main()
