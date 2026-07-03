from shutil import copyfile


output_file = './output/trail_sign.txt'
def uarm_sign_by_aisr(file_path):
    
        by_aisr = [
            [(56, 50), (56, 116)], 
            [(59, 49), (74, 47), (92, 50), (98, 57), (99, 66), (89, 76), (71, 79), (60, 80), (73, 80), (85, 80), (96, 85), (103, 94), (99, 109), (90, 113), (77, 114), (56, 115)], 
            [(122, 45), (147, 82), (148, 114)], 
            [(178, 44), (149, 83)], 
            [(239, 49), (211, 114)], 
            [(240, 51), (268, 114)], 
            [(221, 92), (256, 89)], 
            [(291, 46), (290, 114)], 
            [(357, 62), (339, 46), (323, 53), (322, 73), (336, 80), (350, 83), (364, 96), (358, 107), (341, 116), (326, 116), (313, 101)], 
            [(385, 54), (385, 116)],
            [(387, 49), (423, 49), (431, 54), (437, 69), (430, 78), (421, 83), (399, 83), (390, 81), (413, 82), (427, 101), (440, 116)]
        ]
        by_aisr = [ [ [490 - p[0],p[1]] for p in ps  ] for ps in by_aisr ]


        copyfile(file_path, output_file)
        file3 = open(output_file, 'a')
        # file3 = open('/mnt/ros2/src/trail_sign.txt', 'w')
        contours = by_aisr
        dx = 10
        dy = 70
        f = 0.08
        for c in contours:

            print(str(c[0][0]) + ' '+str(c[0][1])+' '+'0'+'\n')
            file3.write(str(c[0][0]*f+dx) + ' '+str(c[0][1]*f + dy)+' '+'0'+'\n')
            file3.write(str(c[0][0]*f+dx) + ' '+str(c[0][1]*f + dy)+' '+'-33'+'\n')

            for p in c[1:]:
                file3.write(str(p[0]*f+dx) + ' '+str(p[1]*f+dy)+' '+'0'+'\n')

            file3.write(str(p[0]*f+dx) + ' '+str(p[1]*f+dy)+' '+'33'+'\n')

        file3.close()
        return



if __name__ == "__main__":
    uarm_sign_by_aisr("results/test.txt")