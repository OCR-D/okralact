import tarfile

def rename_file(filename, files_list):
    if filename in files_list:
        i = 0
        newname = '.'.join(filename.split('.')[:-2]) + '_%d.tar.gz' % i
        while newname in files_list:
            i += 1
            newname = '.'.join(filename.split('.')[:-2]) + '_%d.tar.gz' % i
        filename = newname
    return filename
