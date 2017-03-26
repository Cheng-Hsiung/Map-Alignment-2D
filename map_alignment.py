from __future__ import print_function

import sys
if sys.version_info[0] == 3:
    from importlib import reload
elif sys.version_info[0] == 2:
    pass

new_paths = [
    u'../arrangement/',
    u'../place_categorization_2D',
    # u'/home/saesha/Dropbox/myGits/Python-CPD/'
]
for path in new_paths:
    if not( path in sys.path):
        sys.path.append( path )

import time
import copy
import itertools 

import cv2
import numpy as np
import sympy as sym
import networkx as nx
import scipy
import scipy.ndimage
import sklearn.cluster
import collections
import numpy.linalg
import skimage.transform

import matplotlib.path as mpath
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.transforms

# import arrangement.arrangement as arr
# reload(arr)
import arrangement.utils as utls
reload(utls)
import arrangement.plotting as aplt
reload(aplt)
import place_categorization as plcat
reload(plcat)


################################################################################
dir_layout = '/home/saesha/Dropbox/myGits/sample_data/'
dir_tango = '/home/saesha/Documents/tango/'

data_sets = {
    # layouts
    'HIH_layout':     dir_layout+'HH/HIH/HIH_04.png',
    'E5_layout':      dir_layout+'HH/E5/E5_06.png',
    'F5_layout':      dir_layout+'HH/F5/F5_04.png',
    'kpt4a_layout':   dir_layout+'sweet_home/kpt4a.png',

    # tango maps
    'HIH_tango':      dir_tango+'HIH_01_full/20170131135829.png',

    'kpt4a_f_tango':  dir_tango+'kpt4a_f/20170131163311.png',
    'kpt4a_kb_tango': dir_tango+'kpt4a_kb/20170131163634.png',
    'kpt4a_kl_tango': dir_tango+'kpt4a_kl/20170131162628.png',
    'kpt4a_lb_tango': dir_tango+'kpt4a_lb/20170131164048.png',

    'E5_01_tango':    dir_tango+'E5_1/20170131150415.png',
    'E5_02_tango':    dir_tango+'E5_2/20170131131405.png',
    'E5_03_tango':    dir_tango+'E5_3/20170131130616.png',
    'E5_04_tango':    dir_tango+'E5_4/20170131122040.png',
    'E5_05_tango':    dir_tango+'E5_5/20170205104625.png',  
    'E5_06_tango':    dir_tango+'E5_6/20170205105917.png',
    'E5_07_tango':    dir_tango+'E5_7/20170205111301.png',
    'E5_08_tango':    dir_tango+'E5_8/20170205112339.png',
    'E5_09_tango':    dir_tango+'E5_9/20170205110552.png',
    'E5_10_tango':    dir_tango+'E5_10/20170205111807.png',
    
    'F5_01_tango':    dir_tango+'F5_1/20170131132256.png',
    'F5_02_tango':    dir_tango+'F5_2/20170131125250.png',
    'F5_03_tango':    dir_tango+'F5_3/20170205114543.png',
    'F5_04_tango':    dir_tango+'F5_4/20170205115252.png',
    'F5_05_tango':    dir_tango+'F5_5/20170205115820.png',
    'F5_06_tango':    dir_tango+'F5_6/20170205114156.png'
}






################################################################################
def find_face2face_association_fast(faces_src, faces_dst):
    '''
    problems:
    this does not result in a one to one assignment
    '''

    face_area_src = np.array([face.get_area() for face in faces_src])
    face_area_dst = np.array([face.get_area() for face in faces_dst])
    # cdist expects 2d arrays as input, so I just convert the 1d area value
    # to 2d vectors, all with one (or any aribitrary number)
    face_area_src_2d = np.stack((face_area_src, np.ones((face_area_src.shape))),axis=1)
    face_area_dst_2d = np.stack((face_area_dst, np.ones((face_area_dst.shape))),axis=1)
    f2f_distance = scipy.spatial.distance.cdist(face_area_src_2d,
                                                face_area_dst_2d,
                                                'euclidean')

    face_cen_src = np.array([face.attributes['centre'] for face in faces_src])
    face_cen_dst = np.array([face.attributes['centre'] for face in faces_dst])
        
    f2f_association = {}
    for src_idx in range(f2f_distance.shape[0]):
        # if the centre of faces in dst are not inside the current face of src
        # their distance are set to max, so that they become illegible
        # TODO: should I also check for f_dst.path.contains_point(face_cen_src)

        f_src = faces_src[src_idx]
        contained_in_src = f_src.path.contains_points(face_cen_dst)
        contained_in_dst = [f_dst.path.contains_point(face_cen_src[src_idx])
                            for f_dst in faces_dst]
        contained = np.logical_and( contained_in_src, contained_in_dst)
        if any(contained):
            maxDist = f2f_distance[src_idx,:].max()
            distances = np.where(contained,
                                 f2f_distance[src_idx,:],
                                 np.repeat(maxDist, contained.shape[0] ))
            dst_idx = np.argmin(distances)
            f2f_association[src_idx] = dst_idx
        else:
            # no face of destination has center inside the current face of src
            pass

    return f2f_association

################################################################################
def arrangement_match_score_fast(arrangement_src, arrangement_dst, tform):
    '''
    '''
    # construct a matplotlib transformation instance (for transformation of paths )
    aff2d = matplotlib.transforms.Affine2D( tform.params )

    ### making a deepcopy of each arrangements, so not to disturb original copy
    arrange_src = copy.deepcopy(arrangement_src)
    arrange_dst = copy.deepcopy(arrangement_dst)

    ### get the area of the arrange_src
    superface_src = arrange_src._get_independent_superfaces()[0]
    superface_src.path = superface_src.path.transformed( aff2d )
    arrange_src_area = superface_src.get_area()

    ### get the area of the arrange_dst
    superface_dst = arrange_dst._get_independent_superfaces()[0]
    # superface_dst.path = superface_dst.path.transformed( aff2d )
    arrange_dst_area = superface_dst.get_area()

    ### transforming paths of faces, and updating centre points 
    faces_src = arrange_src.decomposition.faces
    for face in faces_src:
        face.path = face.path.transformed(aff2d)
        face.attributes['centre'] = np.mean(face.path.vertices[:-1,:], axis=0)

    faces_dst = arrange_dst.decomposition.faces
    for face in faces_dst:
        # face.path = face.path.transformed(aff2d)
        face.attributes['centre'] = np.mean(face.path.vertices[:-1,:], axis=0)
    
    # find face to face association
    f2f_association = find_face2face_association_fast(faces_src, faces_dst)

    # find face to face match score (of associated faces)
    f2f_match_score = {(f1_idx,f2f_association[f1_idx]): None
                       for f1_idx in f2f_association.keys()}
    for (f1_idx,f2_idx) in f2f_match_score.keys():
        score = face_match_score(faces_src[f1_idx],
                                 faces_dst[f2_idx])
        f2f_match_score[(f1_idx,f2_idx)] = score

    # find the weights of pairs of associated faces to arrangement match score
    face_pair_weight = {}
    for (f1_idx,f2_idx) in f2f_match_score.keys():
        f1_area = faces_src[f1_idx].get_area()
        f2_area = faces_dst[f2_idx].get_area()
    
        f1_w = float(f1_area) / float(arrange_src_area)
        f2_w = float(f2_area) / float(arrange_dst_area)
        
        face_pair_weight[(f1_idx,f2_idx)] = np.min([f1_w, f2_w])

    # computing arrangement match score
    arr_score = np.sum([face_pair_weight[(f1_idx,f2_idx)]*f2f_match_score[(f1_idx,f2_idx)]
                        for (f1_idx,f2_idx) in f2f_match_score.keys()])

    return arr_score












################################################################################
def arrangement_match_score(arrangement1, arrangement2):
    '''
    '''

    # find the area of each arrangement
    superface1 = arrangement1._get_independent_superfaces()[0]
    superface2 = arrangement2._get_independent_superfaces()[0]

    arrangement1_area = superface1.get_area()
    arrangement2_area = superface2.get_area()

    # find face to face association
    f2f_association = find_face2face_association(arrangement1,
                                                 arrangement2,
                                                 distance='area')

    # find face to face match score (of associated faces)
    f2f_match_score = {(f1_idx,f2f_association[f1_idx]): None
                       for f1_idx in f2f_association.keys()}
    for (f1_idx,f2_idx) in f2f_match_score.keys():
        score = face_match_score(arrangement1.decomposition.faces[f1_idx],
                                 arrangement2.decomposition.faces[f2_idx])
        f2f_match_score[(f1_idx,f2_idx)] = score

    # find the weights of pairs of associated faces to arrangement match score
    face_pair_weight = {}
    for (f1_idx,f2_idx) in f2f_match_score.keys():
        f1_area = arrangement1.decomposition.faces[f1_idx].get_area()
        f2_area = arrangement2.decomposition.faces[f2_idx].get_area()

        f1_w = float(f1_area) / float(arrangement1_area)
        f2_w = float(f2_area) / float(arrangement2_area)

        face_pair_weight[(f1_idx,f2_idx)] = np.min([f1_w, f2_w])

    # computing arrangement match score
    arr_score = np.sum([face_pair_weight[(f1_idx,f2_idx)]*f2f_match_score[(f1_idx,f2_idx)]
                        for (f1_idx,f2_idx) in f2f_match_score.keys()])

    return arr_score

################################################################################
def face_match_score(face1, face2):
    '''
    NOTE
    ----
    This face_match_score idea is based on the assumption that the level of abstraction between the two maps are
    comparable. Or is it? The face_match_score is used for all variation of alignment (hypotheses) between the same
    two maps, so the dicrepency between levels of abstraction shoudl affect the face_match_score of all hypitheses
    uniformly

    NOTE
    ----
    Union and intersection area are computed by pixelating the paths
    Obviously this is an approximation....
    '''

    # compute the area of intersection and union
    pixels_in_f1 = {tuple(p) for p in get_pixels_in_mpath(face1.path)}
    pixels_in_f2 = {tuple(p) for p in get_pixels_in_mpath(face2.path)}

    union = len( pixels_in_f1.union(pixels_in_f2) )
    intersection = len( pixels_in_f1.intersection(pixels_in_f2) )

    if union == 0:
        # if one of the faces has the area equal to zero 
        return 0.

    # computing overlap ratio and score
    # ratio and score \in [0,1]
    overlap_ratio = float(intersection) / float(union)
    overlap_score = (np.exp(overlap_ratio) - 1) / (np.e-1)

    return overlap_score


################################################################################
def find_face2face_association(arrangement_src, arrangement_dst,
                               distance=['area','centre'][0]):
    '''
    problems:
    this does not result in a one to one assignment
    '''

    # set center coordinate for faces
    set_face_centre_attribute(arrangement_src)
    set_face_centre_attribute(arrangement_dst)
    face_cen_src = np.array([face.attributes['centre']
                             for face in arrangement_src.decomposition.faces])
    face_cen_dst = np.array([face.attributes['centre']
                             for face in arrangement_dst.decomposition.faces])    

    if distance=='area':
        face_area_src = np.array([face.get_area()
                                  for face in arrangement_src.decomposition.faces])
        face_area_dst = np.array([face.get_area()
                                  for face in arrangement_dst.decomposition.faces])
        # cdist expects 2d arrays as input, so I just convert the 1d area value
        # to 2d vectors, all with one (or any aribitrary number)
        face_area_src_2d = np.stack((face_area_src, np.ones((face_area_src.shape))),axis=1)
        face_area_dst_2d = np.stack((face_area_dst, np.ones((face_area_dst.shape))),axis=1)
        f2f_distance = scipy.spatial.distance.cdist(face_area_src_2d,
                                                    face_area_dst_2d,
                                                    'euclidean')
    elif distance=='centre':
        f2f_distance = scipy.spatial.distance.cdist(face_cen_src,
                                                    face_cen_dst,
                                                    'euclidean')
        
    f2f_association = {}
    for src_idx in range(f2f_distance.shape[0]):
        # if the centre of faces in dst are not inside the current face of src
        # their distance are set to max, so that they become illegible
        # TODO: should I also check for f_dst.path.contains_point(face_cen_src)

        f_src = arrangement_src.decomposition.faces[src_idx]
        contained_in_src = f_src.path.contains_points(face_cen_dst)
        contained_in_dst = [f_dst.path.contains_point(face_cen_src[src_idx])
                            for f_dst in arrangement_dst.decomposition.faces]
        contained = np.logical_and( contained_in_src, contained_in_dst)
        if any(contained):
            maxDist = f2f_distance[src_idx,:].max()
            distances = np.where(contained,
                                 f2f_distance[src_idx,:],
                                 np.repeat(maxDist, contained.shape[0] ))
            dst_idx = np.argmin(distances)
            f2f_association[src_idx] = dst_idx
        else:
            # no face of destination has center inside the current face of src
            pass

    return f2f_association


################################################################################
def pointset_match_score (src,dst,sigma, tform=None):
    '''
    This method constructs a set of gaussian distributions, each centered at the
    location of points in destination, with a diagonal covariance matix of sigma.
    It evaluates the values of all points in src in all gaussian models.
    The match score is the sum of all evaluation devided by the number of points
    in the src point set.
    '''
    if tform is None: tform = skimage.transform.AffineTransform()

    S = np.array([[sigma,0] , [0,sigma]])
    src_warp = tform._apply_mat(src, tform.params)

    match_score = np.array([ normal_dist(src_warp, M, S) for M in dst ])
    match_score = match_score.sum()
    match_score /= src.shape[0]

    return match_score

################################################################################
def objectivefun_pointset (X , *arg):
    '''
    X: the set of variables to be optimized
    
    src: source point set (model - template)
    dst: destination point set (static scene - target)

    sigma: variance of the normal distributions located at each destination points 
    '''
    tx, ty, s, t = X 
    tform = skimage.transform.AffineTransform(scale=(s,s),
                                              rotation=t,
                                              translation=(tx,ty))

    src, dst, sigma = arg[0], arg[1], arg[2]
    match_score = pointset_match_score (src,dst,sigma, tform)
    error = 1-match_score

    print (error)
    return error


################################################################################
def objectivefun_image (X , *arg):
    '''
    X: the set of variables to be optimized
    
    src: source image (model - template)
    dst: destination image (static scene - target)
    '''
    tx, ty, s, t = X 
    tform = skimage.transform.AffineTransform(scale=(s,s),
                                              rotation=t,
                                              translation=(tx,ty))
    src_image, dst_image = arg[0], arg[1]
    mse, l2 = mse_norm(src_image, dst_image, tform)
    
    return mse


################################################################################
def mse_norm(src_image, dst_image, tform):
    '''

    since I use distance images as input, their median/gaussian blur is not far
    from their own valeus, otherwise for other images, it would be better to apply
    a blurring before computing the errors
    '''
    ###### constructing the paths of mbb for images
    # get the extent of source image
    minX, maxX = 1, src_image.shape[1]-1 #skiping boundary poitns
    minY, maxY = 1, src_image.shape[0]-1 #skiping boundary poitns
    # mbb-path of src before transform
    src_mbb_pts = np.array([[minX,minY],[maxX,minY],[maxX,maxY],[minX,maxY],[minX,minY]])
    src_mbb_path = create_mpath ( src_mbb_pts )    
    # mbb-path of src after transform
    src_warp_mbb_pts = tform._apply_mat(src_mbb_pts, tform.params)
    src_warp_mbb_path = create_mpath ( src_warp_mbb_pts )

    # creat a list of coordinates of all pixels in src, before and after transform
    X = np.arange(minX, maxX, 1)
    Y = np.arange(minY, maxY, 1)
    X, Y = np.meshgrid(X, Y)
    src_idx = np.vstack( (X.flatten(), Y.flatten()) ).T
    src_idx_warp = tform._apply_mat(src_idx, tform.params).astype(int)
    
    # get the extent of destination image
    minX, maxX = 1, dst_image.shape[1]-1 #skiping boundary poitns
    minY, maxY = 1, dst_image.shape[0]-1 #skiping boundary poitns
    # creat a list of coordinates of all pixels in dst
    X = np.arange(minX, maxX, 1)
    Y = np.arange(minY, maxY, 1)
    X, Y = np.meshgrid(X, Y)
    dst_idx = np.vstack( (X.flatten(), Y.flatten()) ).T
    # mbb-path of dst
    dst_mbb_pts = np.array([[minX,minY],[maxX,minY],[maxX,maxY],[minX,maxY],[minX,minY]])
    dst_mbb_path = create_mpath ( dst_mbb_pts )
    

    ###### find the area of intersection (overlap) and union
    # easiest way to compute the intersection area is to count the number pixels
    # from one image in the mbb-path of the other.    
    # since the pixels in src_idx_warp are transformed (change of scale), they
    # no longer represent the area, so I have to count the number of dst_idx
    # containted by the src_warp_mbb_path
    in_warped_src_mbb = src_warp_mbb_path.contains_points(dst_idx)
    intersect_area = in_warped_src_mbb.nonzero()[0].shape[0]
    src_warp_area = get_mpath_area(src_warp_mbb_path)
    dst_area = get_mpath_area(dst_mbb_path)
    union_area = src_warp_area + dst_area - intersect_area
    # overlap_ratio = float(intersect_area)/union_area # \in [0,1]
    # overlap_score = np.log2(overlap_ratio+1) # \in [0,1]
    # overlap_error = 1-overlap_score # \in [0,1]
    # if there is no overlap, return high error value
    if intersect_area==0: return 127 , union_area/2.# return average error
    # if intersect_area==0: return 127 , 127*union_area/2.# return average error


    ###### computing l2-norm and MSE 
    # find those pixels of src (after warp) that are inside mbb of dst
    in_dst_mbb = dst_mbb_path.contains_points(src_idx_warp)
    # src_idx = src_idx[in_dst_mbb]
    # src_idx_warp = src_idx_warp[in_dst_mbb]
    src_overlap = src_image[src_idx[in_dst_mbb,1],src_idx[in_dst_mbb,0]]
    dst_overlap = dst_image[src_idx_warp[in_dst_mbb,1], src_idx_warp[in_dst_mbb,0]]

    # compute l2-norm
    l2 =  (src_overlap - dst_overlap).astype(float)**2
    l2 = np.sum(l2)
    l2 = np.sqrt(l2)
    # compute MSE (l2 averaged over intersection area)
    mse = l2 / float(dst_overlap.shape[0])

    
    if 1: print(mse, l2)
    return  mse, l2  # * overlap_error

################################################################################
def get_mpath_area(path):
    '''
    TODO:
    Isn't this based on the assumption that the path in convex?
    '''

    polygon = path.to_polygons()
    x = polygon[0][:,0]
    y = polygon[0][:,1]
    PolyArea = 0.5*np.abs(np.dot(x,np.roll(y,1))-np.dot(y,np.roll(x,1)))
    return PolyArea

################################################################################
def create_svgpath_from_mbb(image):
    '''
    Assuming the image starts at origin, and is aligned with main axes, this 
    method returns a svg-path around the image
    
    example
    -------
    path = create_svgpath_from_mbb(img)
    path.area()
    '''
    import svgpathtools
    minX, maxX = 0, image.shape[1]
    minY, maxY = 0, image.shape[0]
    path = svgpathtools.Path( svgpathtools.Line(minX+minY*1j, maxX+minY*1j),
                              svgpathtools.Line(maxX+minY*1j, maxX+maxY*1j),
                              svgpathtools.Line(maxX+maxY*1j, minX+maxY*1j),
                              svgpathtools.Line(minX+maxY*1j, minX+minY*1j) )
    assert path.isclosed()
    return path



################################################################################
def normal_dist_single_input (X, M, S):
    '''
    Inputs
    ------
    X: input point (1xd), where d is the dimension
    M: center of the normal distribution (1xd)
    S: covariance matrix of the normal distribution (dxd)

    Output
    ------
    res (scalar, float)    

    example
    -------
    >>> X = np.array([11,12])
    >>> M = np.array([10,10])
    >>> S = np.array([ [.5,0] , [0,.5] ])
    >>> print normal_dist_single_input(X,M,S)
    0.00214475514
    '''

    if np.abs(np.linalg.det(S)) < np.spacing(10):
        return None

    dis = X-M
    # dis is 1xd vector, transpose of normal math convention
    # that's why the transposes in the nomin are exchanged 
    nomin = np.exp( -.5 * np.dot( np.dot( dis, np.linalg.inv(S)), dis) )
    denom = np.sqrt( np.linalg.det( 2* np.pi* S) )
    res = nomin/denom
    return res


################################################################################
def normal_dist (X, M, S):
    '''
    This method evaluates the value of a normal distribution at every point
    in the input array, and returns as many values in output

    Inputs
    ------
    X: input points (nxd), where n is the number of points and d is the dimension
    M: center of the normal distribution (1xd)
    S: covariance matrix of the normal distribution (dxd)

    Output
    ------
    res (ndarray: 1xn)
    normal distribution's value at each input point

    example
    -------
    >>> X = np.array([ [11,12], [13,14],  [15,16],  [17,18] ])
    >>> M = np.array( [10,10] )
    >>> S = np.array([ [.5,0] , [0,.5] ])
    >>> print normal_dist(X,M,S)
    [  2.14475514e-03   4.42066983e-12   1.02538446e-27   2.67653959e-50]

    Note
    ----
    It won't work if X is (1xd)

    '''
    if np.abs(np.linalg.det(S)) < np.spacing(10):
        return None

    dis = X-M
    nomin = np.exp( -.5* ( np.dot( dis, np.linalg.inv(S)) * dis ).sum(axis=1) )
    denom = np.sqrt( np.linalg.det(2* np.pi* S) )
    res = nomin/denom
    return res




################################################################################
def aff_mat(scale, rotation, translation):
    sx,sy = scale
    t = rotation
    tx,ty = translation
    M = np.array([ [sx*np.cos(t), -sy*np.sin(t), tx*sx*np.cos(t) - ty*sy*sin(t)],
                   [sx*np.sin(t),  sy*np.cos(t), tx*sx*np.sin(t) + ty*sy*cos(t)],
                   [0,             0,            1                             ] ])
    return M

########################################
def rotation_mat_sym(rotation=None):
    t = sym.Symbol('t') if rotation is None else rotation
    R = np.array([ [sym.cos(t), -sym.sin(t), 0],
                   [sym.sin(t),  sym.cos(t), 0],
                   [0,           0,          1] ])
    return R
########################################
def scale_mat_sym(scale=None):
    sx,sy = (sym.Symbol('sx'),sym.Symbol('sy') ) if scale is None else scale
    S = np.array([ [sx, 0,  0],
                   [0,  sy, 0],
                   [0,  0,  1] ])
    return S
########################################
def translation_mat_sym(translation=None):
    tx,ty = (sym.Symbol('tx'), sym.Symbol('ty') ) if translation is None else translation
    T = np.array([ [1, 0, tx],
                   [0, 1, ty],
                   [0, 0, 1 ] ])
    return T


################################################################################
def create_mpath ( points ):
    '''
    note: points must be in order
    - copied from mesh to OGM
    '''
    
    # start path
    verts = [ (points[0,0], points[0,1]) ]
    codes = [ mpath.Path.MOVETO ]

    # construct path - only lineto
    for point in points[1:,:]:
        verts += [ (point[0], point[1]) ]
        codes += [ mpath.Path.LINETO ]

    # close path
    verts += [ (points[0,0], points[0,1]) ]
    codes += [ mpath.Path.CLOSEPOLY ]

    # return path
    return mpath.Path(verts, codes)


################################################################################
def construct_transformation_population(arrangements,
                                        connectivity_maps,
                                        face_similarity=['vote','count',None][0],
                                        tform_type=['similarity','affine'][0],
                                        enforce_match=False):
    '''
    Note
    ----
    connectivity_maps is used to find "label_association" between place categories
    
    if similarity None None connectivity_maps is not needed, since transformations
    among all faces, regardless of their labels, are returned.
    
    Note
    ----
    before calling this method the face.set_shape_descriptor() should be called
        
    '''
    arrange0 = arrangements[arrangements.keys()[0]]
    arrange1 = arrangements[arrangements.keys()[1]]

    # find the alignment pool
    if face_similarity == 'vote':
        # find label association between maps - and remove label -1
        label_associations = label_association(arrangements, connectivity_maps)
        del label_associations[-1]

        tforms = np.array([])
        for lbl0 in label_associations.keys():
            lbl1 = label_associations[lbl0]

            # the first condition for "if" inside list comprehension rejects faces with undesired labels
            # the second condition rejects faces with area==0,
            # because if the area was zero, label_count was set all to zero
            faces0 = [ f_idx
                       for f_idx, face in enumerate(arrange0.decomposition.faces)
                       if (face.attributes['label_vote'] == lbl0) and (np.sum(face.attributes['label_count'].values())>0) ]
            faces1 = [ f_idx
                       for f_idx, face in enumerate(arrange1.decomposition.faces)
                       if (face.attributes['label_vote'] == lbl1) and (np.sum(face.attributes['label_count'].values())>0) ]

            for f0Idx, f1Idx in itertools.product(faces0, faces1):
                tfs_d = utls.align_faces( arrange0, arrange1,
                                          f0Idx, f1Idx,
                                          tform_type=tform_type,
                                          enforce_match=enforce_match)
                tforms = np.concatenate(( tforms,
                                          np.array([tfs_d[k] for k in tfs_d.keys()]) ))

    elif face_similarity == 'count':
        # find label association between maps - and remove label -1
        label_associations = label_association(arrangements, connectivity_maps)
        del label_associations[-1]

        # here again the condition for "if" inside list comprehension rejects faces with area==0,
        # because if the area was zero, label_count was set all to zero
        faces0 = [ f_idx
                   for f_idx, face in enumerate(arrange0.decomposition.faces)
                   if np.sum(face.attributes['label_count'].values()) > 0 ]
        faces1 = [ f_idx
                   for f_idx, face in enumerate(arrange1.decomposition.faces)
                   if np.sum(face.attributes['label_count'].values()) > 0 ]
        
        tforms = np.array([])
        for f0Idx, f1Idx in itertools.product(faces0, faces1):
            face0 = arrange0.decomposition.faces[f0Idx]
            face1 = arrange1.decomposition.faces[f1Idx]
            if are_same_category(face0, face1, label_associations, thr=.4):
                tfs_d = utls.align_faces( arrange0, arrange1,
                                          f0Idx, f1Idx,
                                          tform_type=tform_type,
                                          enforce_match=enforce_match)
                tforms = np.concatenate(( tforms,
                                          np.array([ tfs_d[k]
                                                     for k in tfs_d.keys() ]) ))

    elif face_similarity is None:
        ### find alignments among all faces, regardless of their labels

        # here again the condition for "if" inside list comprehension rejects faces with area==0,
        # because if the area was zero, label_count was set all to zero
        faces0 = [ f_idx
                   for f_idx, face in enumerate(arrange0.decomposition.faces)
                   if np.sum(face.attributes['label_count'].values()) > 0 ]
        faces1 = [ f_idx
                   for f_idx, face in enumerate(arrange1.decomposition.faces)
                   if np.sum(face.attributes['label_count'].values()) > 0  ]

        tforms = np.array([])
        for f0Idx, f1Idx in itertools.product(faces0, faces1):
            tfs_d = utls.align_faces(arrange0, arrange1,
                                     f0Idx, f1Idx,
                                     tform_type=tform_type,
                                     enforce_match=enforce_match)

            tforms = np.concatenate(( tforms,
                                      np.array([tfs_d[k] for k in tfs_d.keys()]) ))

    return tforms

################################################################################
def label_association(arrangements, connectivity_maps):
    '''
    Inputs
    ------
    arrangements (dictionary)
    the keys are the map names and the values are arrangement instances of the maps

    connectivity_maps (dictionary)
    the keys are the map names and the values are connectivity map (graph) instances of the maps
    

    Output
    ------
    association - (dictionary)
    the keys are the labels in the first map (the first key in the arrangements.keys()),
    and the values are the corresponding labels from the second map (the second key in the arrangements.keys())

    Note
    ----
    Assumption: number of categories are the same for both maps


    Note
    ----
    features is a dictionary, storing features of nodes in connectivity maps
    The keys of the features dictionary are: '{:s}_{:d}'.format(map_key, label)
    The labels are feteched from the labels of the corresponding faces in the arrangements
    So the features dictionary has kxl entries (k:number of maps, l:number of labels)

    For features[map_key_l], the value is a numpy.array of (nx2), where:
    n is the number nodes in the current map (map_key) with the same label (label==l)
    Features of nodes are their "degrees" and "load centralities".
    '''

    # assuming the number of cateogries are the same for both maps
    keys = arrangements.keys()
    f = arrangements[keys[0]].decomposition.faces[0]
    labels = [ int(k) for k in f.attributes['label_count'].keys() ]
    
    # assuming label -1 is universal, we'll set it at the end
    labels.pop(labels.index(-1))

    ### constructing the "features" dictionary    
    features = {}
    for key in keys:
        for lbl in labels:
            fs = [ (connectivity_maps[key].node[n_idx]['features'][0], # node degree
                    connectivity_maps[key].node[n_idx]['features'][3]) # node load centrality
                   for n_idx in connectivity_maps[key].node.keys()
                   if arrangements[key].decomposition.faces[n_idx].attributes['label_vote'] == lbl]
            features['{:s}_{:d}'.format(key,lbl)] = np.array(fs)

    ### feature scaling (standardization)
    for key in keys:
        # std and mean of all features in current map (regardless of their place category labels) 
        # TD: should I standardize wrt (mean,std) of all maps?
        all_features = np.concatenate( [ features['{:s}_{:d}'.format(key,lbl)]
                                         for lbl in labels ] )
        std = np.std( all_features, axis=0 )
        mean = np.mean( all_features, axis=0 )
        
        # standardizing all features
        for lbl in labels:
            features['{:s}_{:d}'.format(key,lbl)] -= mean
            features['{:s}_{:d}'.format(key,lbl)] /= std


    # finding associations between labels by minimum distance between their corresponding sets of feature
    # assuming label -1 is universal, we'll set it as default
    associations = {-1:-1}
    for lbl1 in labels:
        S1 = np.cov(  features['{:s}_{:d}'.format(keys[0], lbl1)], rowvar=False )
        U1 = np.mean( features['{:s}_{:d}'.format(keys[0], lbl1)], axis=0 )
        dist = [ bhattacharyya_distance (S1, U1,
                                         S2 = np.cov(  features['{:s}_{:d}'.format(keys[1], lbl2)], rowvar=False ),
                                         U2 = np.mean( features['{:s}_{:d}'.format(keys[1], lbl2)], axis=0 ) )
                 for lbl2 in labels ]

        idx = dist.index(min(dist))
        associations[lbl1] = labels[idx]

    return associations


################################################################################
def bhattacharyya_distance (S1,U1, S2,U2):
    '''
    S: covariance matrix
    U: mean vector

    http://en.wikipedia.org/wiki/Bhattacharyya_distance
    '''

    # sometimes there is only one sample in the feature vector
    # and the resulting covariance is a single number (i.e invalide)
    if S1.shape !=(2,2): S1 = np.eye(2)
    if S2.shape !=(2,2): S2 = np.eye(2)

    S = (S1+S2) /2.0

    U1 = np.atleast_2d(U1)
    U2 = np.atleast_2d(U2)

    if U1.shape[0] > U1.shape[1]: # U1, U2 are (nx1)
        A = (1.0/8) *np.dot( (U1-U2).T, np.dot( np.linalg.inv(S), (U1-U2)) )
    else: #  # U1, U2  are (1xn)
        A = (1.0/8) *np.dot( (U1-U2), np.dot( np.linalg.inv(S), (U1-U2).T) )

    B = (1.0/2) *np.log( np.linalg.det(S) /np.sqrt(np.linalg.det(S1)*np.linalg.det(S2)) )

    return A+B


################################################################################
def profile_nodes(graph):
    '''
    Note:
    nx.eigenvector_centrality - Not defined for multigraphs
    nx.katz_centralit - not implemented for multigraph
    nx.katz_centrality_numpy - not implemented for multigraph
    nx.current_flow_closeness_centrality - only for connected graphs
    nx.edge_betweenness_centrality - for edges
    '''

    # L = nx.laplacian_matrix(connectivity_maps[key])
    L = nx.normalized_laplacian_matrix(graph)
    eigenvalues = numpy.linalg.eigvals(L.A)
    
    eigenvector_centrality = nx.eigenvector_centrality_numpy( graph )
    load_centrality = nx.load_centrality( graph)
    harmonic_centrality = nx.harmonic_centrality( graph )
    degree_centrality = nx.degree_centrality( graph )
    closeness_centrality = nx.closeness_centrality( graph )
    betweenness_centrality = nx.betweenness_centrality( graph )
    

    for idx, key in enumerate( graph.node.keys() ):
        graph.node[key]['features'] = [
            graph.degree()[key],         # node degree
            eigenvalues[idx],            # node eigenvalue
            eigenvector_centrality[key], # node eigenvector centrality
            load_centrality[key],        # node load centrality
            harmonic_centrality[key],    # node harmonic centrality
            degree_centrality[key],      # node degree centrality
            closeness_centrality[key],   # node closeness centrality
            betweenness_centrality[key]  # node betweenness centrality
        ]

    return graph

################################################################################
def get_pixels_in_mpath(path, image_shape=None):
    '''
    given a path and image_size, this method return all the pixels in the path
    that are inside the image
    '''

    # find the extent of the minimum bounding box, sunjected to image boundaries
    mbb = path.get_extents()
    if image_shape is not None:
        xmin = int( np.max ([mbb.xmin, 0]) )
        xmax = int( np.min ([mbb.xmax, image_shape[1]-1]) )
        ymin = int( np.max ([mbb.ymin, 0]) )
        ymax = int( np.min ([mbb.ymax, image_shape[0]-1]) )
    else:
        xmin = int( mbb.xmin )
        xmax = int( mbb.xmax )
        ymin = int( mbb.ymin )
        ymax = int( mbb.ymax )

    x, y = np.meshgrid( range(xmin,xmax+1), range(ymin,ymax+1) )
    mbb_pixels = np.stack( (x.flatten().T,y.flatten().T), axis=1)
    
    in_path = path.contains_points(mbb_pixels)

    return mbb_pixels[in_path, :]

################################################################################
def get_pixels_in_cirlce(pixels, centre, radius):    
    '''
    given a set of pixels, returns those in inside the define circle
    '''    
    ####### find pixels_in_circle:
    # cdist expects post input to be 2d, hence the use of np.atleast_2d
    dists = scipy.spatial.distance.cdist(np.atleast_2d(centre), pixels, 'euclidean')
    # flagging all the points that are in the circle
    # due to cdist's result, the first element on nonzero is a sequence of zeros
    # the first element is an array of row indices, and since dists is 1xx -> rows=0
    pixel_inbound_idx = np.nonzero( dists<=radius )[1]
    return pixels[pixel_inbound_idx]
    
################################################################################
def assign_label_to_face(label_image, face, all_pixels=None):
    '''
    '''
    if all_pixels is None:
        x, y = np.meshgrid( np.arange(label_image.shape[1]),
                            np.arange(label_image.shape[0]))
        all_pixels = np.stack( (x.flatten(), y.flatten() ), axis=1)
        
        
    in_face = face.path.contains_points(all_pixels)
    pixels = all_pixels[in_face, :]

    if pixels.shape[0]==0:
        label = -1
        labels = { lbl: 0. for lbl in np.unique(label_image) }

    else:
        # mode=='vote'
        not_nan = np.nonzero( np.isnan(label_image[pixels[:,1],pixels[:,0]])==False )[0]
        label = np.median(label_image[pixels[:,1],pixels[:,0]][not_nan] )
        label = -1 if np.isnan(label) else label
        
        # mode=='count'
        total = float(pixels.shape[0])
        labels = { lbl: np.nonzero(label_image[pixels[:,1],pixels[:,0]]==lbl)[0].shape[0] /total
                   for lbl in np.unique(label_image)}
        # assert np.abs( np.sum([ labels[lbl] for lbl in labels.keys() ]) -1) < np.spacing(10**5)

    face.attributes['label_vote'] = label
    face.attributes['label_count'] = labels
    # return face


################################################################################
def assign_label_to_all_faces(arrangement, label_image):
    '''
    attributes['label_vote'] (int)
    winner takes all. this contains a single value, that is the most common label in the face

    attributes['label_count'] (dictionary)
    per label in the label_image, there is a key in this dictionary
    the value to each key represents the presence of that label in the face (in percent [0,1]) 
    '''
    # note that all_pixels is in (col,row) format
    # use the same for "path.contains_points" and convert to (row,col) for
    # indexing the label_image
    x, y = np.meshgrid( np.arange(label_image.shape[1]),
                        np.arange(label_image.shape[0]))
    all_pixels = np.stack( (x.flatten(), y.flatten() ), axis=1)
    
    for idx, face in enumerate(arrangement.decomposition.faces):
        # set face attributes ['label_vote'], ['label_count']
        assign_label_to_face(label_image, face, all_pixels=all_pixels)
        # can't set the following since faces is a tuple, and no need to
        # arrangement.decomposition.faces[idx] = face
    
    


################################################################################
def face_category_distance(face1,face2, label_associations=None):
    '''

    label_associations
    keys are the place category labels in face1
    values corresponding to each key are the place category labels in face2
    ie. lbl1 corresponds to lb2 <=> label_associations[lbl1]=lbl2
    if label_associations is None, a direct correspondance is assumed

    Note
    ----
    if label_associations is provided, it is assumed that the its keys correspond
    to face1.attributes['label_count'].keys() and the values in the
    label_associations correspond to face2.attributes['label_count'].keys()

    Note
    ----
    it is assumed that the number of place category labels in the two faces are
    the same;
    ie. len(face1.attributes['label_count']) == len(face2.attributes['label_count'])    
    '''

    # since the difference between lables in face1 and face2 might be non-empty
    # the sequence of if-elif will consider unique labels in each face
    # otherwise they could be set as np.array and compute distance faster.
    # w1 = face1.attributes['label_count']
    # w2 = face2.attributes['label_count']    
    # dis = 0		
    # for lbl in set( w1.keys()+w2.keys() ):
    #     if (lbl in w1) and (lbl in w2):
    #         dis += (w1[lbl]-w2[lbl])**2
    #     elif lbl in w1:
    #         dis += w1[lbl]**2
    #     elif lbl in w2:
    #         dis += w2[lbl]**2            
    # dis = np.sqrt( dis )

    w1 = face1.attributes['label_count']
    w2 = face2.attributes['label_count']

    if label_associations is None:
        # assuming a direct correspondance between w1.keys() and w2.keys()
        label_associations = {key:key for key in w1.keys()}

    w1_arr = np.array([ w1[key]
                        for key in label_associations.keys() ])
    w2_arr = np.array([ w2[label_associations[key]]
                        for key in label_associations.keys() ])

    dis = np.sqrt( np.sum( (w1_arr-w2_arr)**2 ) )

    return dis

################################################################################
def are_same_category(face1,face2, label_associations=None, thr=.4):
    '''
    This method checks if the two input faces are similar according to 
    their place category label (count version)
    for the detials on the "count" version see: assign_label_to_face.__doc__

    Inputs
    ------
    face1, face2 ( Face instances )

    Parameters
    ----------
    label_associations (dictionary, default None)
    if the two faces belong to two different arrangments, there is no gaurantee
    that their labels correctly correspond to each other.
    to get label_associations, call the method "label_association()".
    If not provided (default None), it is assumed the two faces belong to the 
    same arrangement and there for the correspondance are direct.

    thr (float between (0,1), default: 0.4)
    If the distance between the category of faces is below this, the faces are
    assumed to belong to the same category

    Note
    ----
    It is required that the "assign_label_to_face()" method is called
    before calling this method.
    '''
    dis = face_category_distance( face1,face2, label_associations )    
    return True if dis<thr else False


################################################################################
def categorize_faces (image, arrangement,
                      radius = None,
                      n_categories = 2,
                      mpp = 0.02, # meter per pixel
                      range_meter = 8, # meter
                      length_range = 400, #range_meter_ / mpp_
                      length_steps = 200, #int(length_range_)
                      theta_range = 2*np.pi,
                      theta_res = 1/1, # step/degree
                      occupancy_thr = 180,
                      gapThreshold = [1.0]
                  ):
    '''
    raycast from the center of each face, within a circle of "radius"
    '''
    # erode the ogm to make it suitable for raycasting
    kernel = np.ones((5,5),np.uint8)
    raycast_image = cv2.erode(image, kernel, iterations = 1)
    raycast_image = cv2.medianBlur(raycast_image, 5)

    ########## raycast template
    pose_ = np.array([0,0,0]) # x,y,theta
    rays_array_xy = plcat.construct_raycast_array(pose_,
                                                  length_range, length_steps, 
                                                  theta_range, theta_res)
    raxy = rays_array_xy


    ##########
    # storage of the features and their corresponding faces 
    face_idx = np.array([-1])
    features = np.zeros(( 1, 16+len(gapThreshold) ))

    ########## feature extraction per face
    for f_idx, face in enumerate(arrangement.decomposition.faces):
        pc = face.attributes['centre']
        centre = np.array([pc[0],pc[1]])

        # Note that after pruning, can't be sure if the center of face is inside!
        mbb = get_pixels_in_mpath(face.path, raycast_image.shape)
        if radius is None:
            inbounds = mbb
        else:
            inbounds = get_pixels_in_cirlce(mbb, centre, radius)
        
        ###### finding open-cells among pixels_in_circle_in_face
        open_cells_idx = np.nonzero( raycast_image[inbounds[:,1],inbounds[:,0]] >= occupancy_thr+15 )[0]
        open_cells = inbounds[open_cells_idx]


        # if the numebr of open_cells is too small, means that
        # the chosen open_space is more like a small pocket
        # so it won't result any proper raycast, svd might fail
        mimimum_openspace_size = 5
        if open_cells.shape[0] > mimimum_openspace_size:

            # per point in the open cells, a feature of len: 16+len(gapThreshold_)
            feat = np.zeros( ( len(open_cells), 16+len(gapThreshold) ) )
            # per pixels, add a new entry to face_idx array, corresponding to face index
            fc_ix = np.ones( len(open_cells) ) * int(f_idx)

            # raycasting and feature extraction from each pixel in open_cells
            for p_idx,(x,y) in enumerate(open_cells):

                pose_ = np.array([x,y,0]) # x,y,theta

                r,t = plcat.raycast_bitmap(raycast_image, pose_,
                                           occupancy_thr,
                                           length_range, length_steps, 
                                           theta_range, theta_res,
                                           rays_array_xy=raxy)

                feat[p_idx,:] = plcat.raycast_to_features(t,r,
                                                          mpp=mpp,
                                                          RLimit=range_meter,
                                                          gapThreshold=gapThreshold)

            features = np.concatenate( (features, feat) , axis=0)
            face_idx = np.concatenate( (face_idx, fc_ix) )

        
    ########## clustering
        
    ### feature modification
    X = features
    ## Normalizing 
    for i in range(X.shape[1]):
        X[:,i] /= X[:,i].mean()
    # rejectin NaNs
    X = np.where ( np.isnan(X), np.zeros(X.shape) , X) 
    
    ### clustering 
    kmean = sklearn.cluster.KMeans(n_clusters=n_categories,
                                   precompute_distances=False,
                                   n_init=20, max_iter=500)
    kmean.fit(X)
    labels = kmean.labels_
    
    
    ########## face labeling with voting
    for f_idx in np.arange(len(arrangement.decomposition.faces)):
        idx = np.nonzero(face_idx==f_idx)
        # if a face_center was rejected as pocket, its label is -1
        if len(idx[0]) > 0:
            l = np.median(labels[idx])
        else:
            l = -1
        arrangement.decomposition.faces[f_idx].attributes['label'] = l

    return arrangement

################################################################################
def set_face_centre_attribute(arrangement,
                              source=['nodes','path'][0]):
    '''
    assumes all the faces in arrangement are convex
    
    if source == 'nodes' -> centre from nodes of arrangement
    if source == 'path' -> centre from vertrices of the face
    (for source == 'path', path must be up-todate)
    '''
    for face in arrangement.decomposition.faces:

        if source == 'nodes':
            nodes = [arrangement.graph.node[fn_idx]
                     for fn_idx in face.get_all_nodes_Idx()]
            xc = np.mean([ node['obj'].point.x for node in nodes ])
            yc = np.mean([ node['obj'].point.y for node in nodes ])
            face.attributes['centre'] = [float(xc),float(yc)]
        elif source == 'path':
            face.attributes['centre'] = np.mean(face.path.vertices[:-1,:], axis=0)

################################################################################
def construct_connectivity_map(arrangement, set_coordinates=True):
    '''

    Parameter:
    set_coordinates: Boolean (default:True)
    assumes all the faces in arrangement are convex, and set the coordinate of
    each corresponding node in the connectivity-map to the center of gravity of
    the face's nodes

    Note
    ----
    The keys to nodes in connectivity_map corresponds to 
    face indices in the arrangement
    '''

    connectivity_map = nx.MultiGraph()

    if set_coordinates: set_face_centre_attribute(arrangement)
    faces = arrangement.decomposition.faces

    ########## node construction (one node per each face)
    nodes = [ [f_idx, {}] for f_idx,face in enumerate(faces) ]
    connectivity_map.add_nodes_from( nodes )

    # assuming convex faces, node coordinate = COG (face.nodes)
    if set_coordinates:
        for f_idx,face in enumerate(faces):
            connectivity_map.node[f_idx]['coordinate'] = face.attributes['centre']

    ########## edge construction (add if faces are neighbor and connected)
    corssed_halfedges = [ (s,e,k)
                          for (s,e,k) in arrangement.graph.edges(keys=True)
                          if arrangement.graph[s][e][k]['obj'].attributes['crossed'] ]

    # todo: detecting topologically distict connection between face
    # consider this:
    # a square with a non-tangent circle enclosed and a vetical line in middle
    # the square.substract(circle) region is split to two and they are connected
    # through two topologically distict paths. hence, the graph of connectivity
    # map must be multi. But if two faces are connected with different pairs of 
    # half-edge that are adjacent, these connection pathes are not topologically
    # distict, hence they should be treated as one connection

    # todo: if the todo above is done, include it in dual_graph of the 
    # arrangement

    # for every pair of faces an edge is added if
    # faces are neighbours and the shared-half_edges are crossed 
    for (f1Idx,f2Idx) in itertools.combinations( range(len(faces) ), 2):
        mutualHalfEdges = arrangement.decomposition.find_mutual_halfEdges(f1Idx, f2Idx)
        mutualHalfEdges = list( set(mutualHalfEdges).intersection(set(corssed_halfedges)) )
        if len(mutualHalfEdges) > 0:
            connectivity_map.add_edges_from( [ (f1Idx,f2Idx, {}) ] )
            
    return arrangement, connectivity_map


################################################################################
def skiz_bitmap (image, invert=True, return_distance=False):
    '''
    Skeleton of Influence Zone [AKA; Generalized Voronoi Diagram (GVD)]

    Input
    -----
    Bitmap image (occupancy map)
    occupied regions: low value (black), open regions: high value (white)

    Parameter
    ---------
    invert: Boolean (default:False)
    If False, the ridges will be high (white) and backgroud will be low (black) 
    If True, the ridges will be low (black) and backgroud will be high (white) 

    Output
    ------
    Bitmap image (Skeleton of Influence Zone)


    to play with
    ------------
    > the threshold (.8) multiplied with grd_abs.max()
    grd_binary_inv = np.where( grd_abs < 0.8*grd_abs.max(), 1, 0 )
    > Morphology of the input image
    > Morphology of the grd_binary_inv
    > Morphology of the skiz
    '''

    original = image.copy()

    ###### image erosion to thicken the outline
    kernel = np.ones((9,9),np.uint8)
    image = cv2.erode(image, kernel, iterations = 1)
    # image = cv2.medianBlur(image, 5)
    # image = cv2.GaussianBlur(image, (5,5), 0).astype(np.uint8)
    # image = cv2.erode(image, kernel, iterations = 1) 
    image = cv2.medianBlur(image, 5)

    ###### compute distance image
    dis = scipy.ndimage.morphology.distance_transform_bf( image )
    # dis = scipy.ndimage.morphology.distance_transform_cdt(image)
    # dis = scipy.ndimage.morphology.distance_transform_edt(image)

    ###### compute gradient of the distance image
    dx = cv2.Sobel(dis, cv2.CV_64F, 1,0, ksize=5)
    dy = cv2.Sobel(dis, cv2.CV_64F, 0,1, ksize=5)
    grd = dx - 1j*dy
    grd_abs = np.abs(grd)

    # at some points on the skiz tree, the abs(grd) is very weak
    # this erosion fortifies those points 
    kernel = np.ones((3,3),np.uint8)
    grd_abs = cv2.erode(grd_abs, kernel, iterations = 1)

    # only places where gradient is low
    grd_binary_inv = np.where( grd_abs < 0.8*grd_abs.max(), 1, 0 )
    
    ###### skiz image
    # sometimes the grd_binary_inv becomes high value near the boundaries
    # the erosion of the image means to extend the low-level boundaries
    # and mask those undesired points
    kernel = np.ones((5,5),np.uint8)
    image = cv2.erode(image, kernel, iterations = 1)    
    skiz = (grd_binary_inv *image ).astype(np.uint8)

    # ###### map to [0,255]
    # skiz = (255 * skiz.astype(np.float)/skiz.max()).astype(np.uint8)

    ###### sometimes border lines are marked, I don't link it!
    # skiz[:,0] = 0
    # skiz[:,skiz.shape[1]-1] = 0
    # skiz[0,:] = 0
    # skiz[skiz.shape[0]-1,:] = 0


    # ###### post-processing
    kernel = np.ones((3,3),np.uint8)
    skiz = cv2.dilate(skiz, kernel, iterations = 1)
    skiz = cv2.erode(skiz, kernel, iterations = 1)
    skiz = cv2.medianBlur(skiz, 3)
    # kernel = np.ones((3,3),np.uint8)
    # skiz = cv2.dilate(skiz, kernel, iterations = 1)

    ###### inverting 
    if invert:
        thr1,thr2 = [127, 255]
        ret, skiz = cv2.threshold(skiz , thr1,thr2 , cv2.THRESH_BINARY_INV)
        
    ###### plottig - for the debuging and fine-tuning    
    internal_plotting = False
    if internal_plotting:

        import matplotlib.gridspec as gridspec
        gs = gridspec.GridSpec(2, 3)
        
        # image
        ax1 = plt.subplot(gs[0, 0])
        ax1.set_title('original')
        ax1.imshow(original, cmap = 'gray', interpolation='nearest', origin='lower')
        
        # image_binary
        ax2 = plt.subplot(gs[1, 0])
        ax2.set_title('image')
        ax2.imshow(image, cmap = 'gray', interpolation='nearest', origin='lower')
        
        # dis
        ax3 = plt.subplot(gs[0, 1])
        ax3.set_title('dis')
        ax3.imshow(dis, cmap = 'gray', interpolation='nearest', origin='lower')
        
        # grd_binary
        ax4 = plt.subplot(gs[1, 1])
        ax4.set_title('abs(grd) [binary_inv]')
        ax4.imshow(grd_abs, cmap = 'gray', interpolation='nearest', origin='lower')
        # ax4.imshow(grd_binary_inv, cmap = 'gray', interpolation='nearest', origin='lower')
        
        # voronoi
        ax5 = plt.subplot(gs[:, 2])
        ax5.set_title('skiz')
        ax5.imshow(skiz, cmap = 'gray', interpolation='nearest', origin='lower')

    plt.show()


    if return_distance:
        return skiz, dis
    elif not(return_distance):
        return skiz


################################################################################
def set_edge_crossing_attribute(arrangement, skiz,
                                neighborhood=3, cross_thr=12):
    '''
    Parameters
    ----------
    neighborhood = 5 # the bigger, I think the more robust it is wrt skiz-noise
    cross_thr = 4 # seems a good guess! smaller also works
    
    Note
    ----
    skiz lines are usually about 3 pixel wide, so a proper edge crossing would
    result in about (2*neighborhood) * 3pixels ~ 6*neighborhood
    for safty, let's set it to 3*neighborhood

    for a an insight to its distributions:
    >>> plt.hist( [arrangement.graph[s][e][k]['obj'].attributes['skiz_crossing'][0]
                   for (s,e,k) in arrangement.graph.edges(keys=True)],
                  bins=30)
    >>> plt.show()

    Note
    ----
    since "set_edge_occupancy" counts low_values as occupied,
    (invert=True) must be set when calling the skiz_bitmap 
    '''

    set_edge_occupancy(arrangement,
                       skiz, occupancy_thr=127,
                       neighborhood=neighborhood,
                       attribute_key='skiz_crossing')


    for (s,e,k) in arrangement.graph.edges(keys=True):
        o, n = arrangement.graph[s][e][k]['obj'].attributes['skiz_crossing']
        arrangement.graph[s][e][k]['obj'].attributes['crossed'] = False if o <= cross_thr else True

    # since the outer part of arrangement is all one face (Null),
    # I'd rather not have any of the internal faces be connected with Null
    # that might mess up the structure/topology of the connectivity graph
    forbidden_edges  = arrangement.get_boundary_halfedges()
    for (s,e,k) in forbidden_edges:
        arrangement.graph[s][e][k]['obj'].attributes['crossed'] = False
        (ts,te,tk) = arrangement.graph[s][e][k]['obj'].twinIdx
        arrangement.graph[ts][te][tk]['obj'].attributes['crossed'] = False
    return skiz


################################################################################
def get_nodes_to_prune (arrangement, low_occ_percent, high_occ_percent):
    '''
    This method returns a list of nodes to be removed from the arrangement.
    Node pruning rules:
    - rule 1: low node occupancy | below "low_occ_percent"
    - rule 2: no edge with high edge_occupancy | not more than "high_occ_percent"
    - rule 3: connected to no edge in forbidden edges
    for the explanation of forbidden_edges, see the note below
    
    Input
    -----
    arrangement

    Parameter
    ---------
    low_occ_percent: float between (0,1)
    high_occ_percent: float between (0,1)
    For their functionality see the description of the rules.
    Their value comes from the histogram of the occupancy ratio of the nodes and edges.
    execute "plot_node_edge_occupancy_statistics(arrangement) to see the histograms.
    I my experience, there are two peaks in the histograms, one close adjacent to zero
    and another one around .05.
    low_occ_percent is set slighlty after the first peak (~.02)
    high_occ_percent is set slighlty before the second peak (~.04)

    Output
    ------
    nodes_to_prune:
    list of node keys


    Note
    ----
    This method uses the occupancy values stored in the edges and nodes' attribute
    arrangement.graph[s][e][k]['obj'].attributes['occupancy']
    arrange.graph.node[s]['obj'].attributes['occupancy']
    Before calling this method, make sure they are set.

    Note
    ----
    fobidden_edge: edges that belong to the baoundary of the arrangement
    their removal will open up faces, hence undesired.
    must be checked in both edge-prunning and ALSO node prunning
    removing a node that will remove a forbidden edge is undesired
    the forbidden nodes are reflected in the forbidden edges, i.e a node that its
    removal would remove a forbidden edge.
    '''
    forbidden_edges  = arrangement.get_boundary_halfedges()
    nodes_to_prune = []
    for n_idx in arrangement.graph.node.keys():

        # rule 1
        o,n = arrangement.graph.node[n_idx]['obj'].attributes['occupancy']
        node_is_open = float(o)/n < low_occ_percent

        # rules 2 and 3
        edges_are_open = True
        edges_not_forbiden = True
        for (s,e,k) in arrangement.graph.out_edges([n_idx], keys=True):
            edges_not_forbiden = edges_not_forbiden and ((s,e,k) not in forbidden_edges)
            o, n = arrangement.graph[s][e][k]['obj'].attributes['occupancy']
            edges_are_open = edges_are_open and (float(o)/n < high_occ_percent)

        if node_is_open and edges_are_open and edges_not_forbiden:
            nodes_to_prune += [n_idx]

    return nodes_to_prune

################################################################################
def get_edges_to_purge (arrangement,
                        low_occ_percent, high_occ_percent,
                        consider_categories=True):
    '''
    This method returns a list of edges to be removed from the arrangement.
    Edge pruning rules:
    - rule 1: (self and twin) not in forbidden_edges
    - rule 2: low_edge_occupancy - self below "low_occ_percent"
    - rule 3: not_high_node_occupancy - no nodes with more than "high_occ_percent"
    for the explanation of forbidden_edges, see the note below    

    Input
    -----
    arrangement

    Parameter
    ---------
    low_occ_percent: float between (0,1)
    high_occ_percent: float between (0,1)
    For their functionality see the description of the rules.
    Their value comes from the histogram of the occupancy ratio of the nodes and edges.
    execute "plot_node_edge_occupancy_statistics(arrangement) to see the histograms.
    I my experience, there are two peaks in the histograms, one close adjacent to zero
    and another one around .05.
    low_occ_percent is set slighlty after the first peak (~.02)
    high_occ_percent is set slighlty before the second peak (~.04)

    consider_categories
    If consider_categories is True, "forbidden_edges" will include, in addition
    to boundary edges, those edges in between two faces with different place
    category labels.

    Output
    ------
    edges_to_purge: list of tuples [(s,e,k), ... ]

    Note
    ----
    This method uses the occupancy values stored in the edges and nodes' attribute
    arrangement.graph[s][e][k]['obj'].attributes['occupancy']
    arrange.graph.node[s]['obj'].attributes['occupancy']
    Before calling this method, make sure they are set.

    Note
    ----
    fobidden_edge: edges that belong to the baoundary of the arrangement
    their removal will open up faces, hence undesired.
    must be checked in both edge-prunning and ALSO node prunning
    removing a node that will remove a forbidden edge is undesired
    the forbidden nodes are reflected in the forbidden edges, i.e a node that its
    removal would remove a forbidden edge.
    '''

    forbidden_edges  = arrangement.get_boundary_halfedges()

    ###
    if consider_categories:
        low_occ_percent *= 10#4
        # high_occ_percent *= .5
        
        for (f1Idx, f2Idx) in itertools.combinations( range(len(arrangement.decomposition.faces)), 2):
            face1 = arrangement.decomposition.faces[f1Idx]
            face2 = arrangement.decomposition.faces[f2Idx]
            # note that we are comparing faces inside the same arrangment
            # so the label_associations is None (ie direct association)
            # with higher thr (thr=.8), I'm being generous on similarity 
            if not( are_same_category(face1,face2, label_associations=None, thr=.4) ):
            # if ( face1.attributes['label_vote'] != face2.attributes['label_vote']):
                forbidden_edges.extend( arrangement.decomposition.find_mutual_halfEdges(f1Idx, f2Idx) )

    # todo: raise an error if 'occupancy' is not in the attributes of the nodes and edges

    edges_to_purge = []
    for (s,e,k) in arrangement.graph.edges(keys=True):
        
        # rule 1: (self and twin) not in forbidden_edges
        not_forbidden = (s,e,k) not in forbidden_edges
        # for a pair of twin half-edge, it's possible for one to be in forbidden list and the other not
        # so if the occupancy suggests that they should be removed, one of them will be removed
        # this is problematic for arrangement._decompose, I can't let this happen! No sir!
        (ts,te,tk) = arrangement.graph[s][e][k]['obj'].twinIdx
        not_forbidden = not_forbidden and  ((ts,te,tk) not in forbidden_edges)
        
        # rule 2: low_edge_occupancy - below "low_occ_percent"
        o, n = arrangement.graph[s][e][k]['obj'].attributes['occupancy']
        edge_is_open = float(o)/n < low_occ_percent
        
        # rule 3: not_high_node_occupancy - not more than "high_occ_percent"
        o,n = arrangement.graph.node[s]['obj'].attributes['occupancy']
        s_is_open = True #float(o)/n < high_occ_percent
        o,n = arrangement.graph.node[e]['obj'].attributes['occupancy']
        e_is_open = True #float(o)/n < high_occ_percent
                
        if not_forbidden and edge_is_open and (s_is_open or e_is_open):
            edges_to_purge.append( (s,e,k) )
    
    for (s,e,k) in edges_to_purge:
        if arrangement.graph[s][e][k]['obj'].twinIdx not in edges_to_purge:
            raise (NameError('there is a half-edge whos twin is not in the "edges_to_purge"'))

    return edges_to_purge


################################################################################
def pixel_neighborhood_of_segment (p1,p2, neighborhood=5):
    '''
    move to arr.utls

    Input:
    ------
    p1 and p2, the ending points of a line segment

    Parameters:
    -----------
    neighborhood:
    half the window size in pixels (default:5)

    Output:
    -------
    neighbors: (nx2) np.array
    

    Note:
    Internal naming convention for the coordinates order is:
    (x,y) for coordinates - (col,row) for image
    However, this method is not concerned with the order.
    If p1 and p2 are passed as (y,x)/(row,col) the output will
    follow the convention in inpnut.
    '''
    # creating a uniform distribution of points on the line
    # for small segments N will be zero, so N = max(2,N)
    N = int( np.sqrt( (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 ) )
    N = np.max([2, N])
    x = np.linspace(p1[0],p2[0], N, endpoint=True)
    y = np.linspace(p1[1],p2[1], N, endpoint=True)
    line_pts = np.stack( (x.T,y.T), axis=1)

    # index to all points in the minimum bounding box (MBB)
    # (MBB of the line from p1 to p2) + margin
    xMin = np.min([ int(p1[0]), int(p2[0]) ]) - neighborhood
    xMax = np.max([ int(p1[0]), int(p2[0]) ]) + neighborhood
    yMin = np.min([ int(p1[1]), int(p2[1]) ]) - neighborhood
    yMax = np.max([ int(p1[1]), int(p2[1]) ]) + neighborhood
    x, y = np.meshgrid( range(xMin,xMax), range(yMin,yMax) )
    mbb_pixels = np.stack( (x.flatten().T,y.flatten().T), axis=1)

    # min distance between points in MBB and the line
    dists = scipy.spatial.distance.cdist(line_pts, mbb_pixels, 'euclidean')
    dists = dists.min(axis=0)

    # flagging all the points that are in the neighborhood
    # of the 
    neighbors_idx = np.nonzero( dists<neighborhood )[0]
    neighbors = mbb_pixels[neighbors_idx]
    
    return neighbors

################################################################################
def pixel_neighborhood_of_halfedge (arrangement, (s,e,k),
                                    neighborhood=5, image_size=None):
    '''
    move to arr.arr
    
    Inputs:
    -------
    arrangement:
    (s,e,k): an index-set to a half-edge    

    Parameters:
    -----------
    neighborhood:
    half the window size in pixels (default:5)

    output:
    -------
    integer coordinate (index) to the half-edge's enighborhood.
    

    Note:
    -----
    output is in this format:
    (x,y) / (col,row)
    for platting use directly
    for image indexing use inverted
    '''

    he = arrangement.graph[s][e][k]['obj']
    trait = arrangement.traits[he.traitIdx]
    pt_1 = arrangement.graph.node[s]['obj'].point
    pt_2 = arrangement.graph.node[e]['obj'].point

    if not( isinstance(trait.obj, (sym.Line, sym.Segment, sym.Ray) ) ):
        raise (NameError(' only line trait are supported for now '))
    
    # Assuming only line segmnent - no arc-circle
    p1 = np.array([pt_1.x,pt_1.y]).astype(float)
    p2 = np.array([pt_2.x,pt_2.y]).astype(float)
    
    neighbors = pixel_neighborhood_of_segment (p1,p2, neighborhood)

    if image_size is None:
        return neighbors
    else:
        xMin, yMin, xMax, yMax = [0,0, image_size[1], image_size[0]]
        x_in_bound = (xMin<=neighbors[:,0]) & (neighbors[:,0]<xMax)
        y_in_bound = (yMin<=neighbors[:,1]) & (neighbors[:,1]<yMax)
        pt_in_bound = x_in_bound & y_in_bound
        in_bound_idx = np.where(pt_in_bound)[0]
        return neighbors[in_bound_idx]

################################################################################
def set_edge_occupancy(arrangement,
                       image, occupancy_thr=200,
                       neighborhood=10,
                       attribute_key='occupancy'):
    '''
    This method sets the occupancy every edge in the arrangement wrt image:
    arrangement.graph[s][e][k]['obj'].attributes[attribute_key] = [occupied, neighborhood_area]

    Inputs
    ------
    arrangement:
    The arrangement corresponding to the input image

    image: bitmap (gray scale)
    The image represensts the occupancy map and has high value for open space.


    Parameters
    ----------
    occupancy_thr: default:200
    Any pixel with value below "occupancy_thr" is considered occupied.

    neighborhood: default=10
    half the window size (ie disk radius) that defines the neighnorhood

    attribute_key: default:'occupancy'
    The key to attribute dictionary of the edges to store the 'occupancy'
    This method is used for measuring occupancy of edges against occupancy map and skiz_map
    Therefor it is important to store the result in the atrribute dictionary with proper key


    Note
    ----
    "neighborhood_area" is dependant on the "neighborhood" parameter and the length of the edge.
    Hence it is the different from edge to edge.
    '''
    for (s,e,k) in arrangement.graph.edges(keys=True):
        neighbors = pixel_neighborhood_of_halfedge (arrangement, (s,e,k),
                                                    neighborhood,
                                                    image_size=image.shape)

        neighbors_val = image[neighbors[:,1], neighbors[:,0]]
        occupied = np.nonzero(neighbors_val<occupancy_thr)[0]
        
        # if neighbors.shape[0] is zero, I will face division by zero
        # when checking for occupancy ratio
        o = occupied.shape[0]
        n = np.max([1,neighbors.shape[0]])

        arrangement.graph[s][e][k]['obj'].attributes[attribute_key] = [o, n]

################################################################################
def set_node_occupancy(arrangement,
                       image, occupancy_thr=200,
                       neighborhood=10,
                       attribute_key='occupancy'):
    '''
    This method sets the occupancy every node in the arrangement wrt image:
    arrangement.graph.node[key]['obj'].attributes[attribute_key] = [occupied, neighborhood_area]

    Inputs
    ------
    arrangement
    The arrangement corresponding to the input image

    image: bitmap (gray scale)
    The image represensts the occupancy map and has high value for open space.

    Parameters
    ----------
    occupancy_thr: default:200
    Any pixel with value below "occupancy_thr" is considered occupied.

    neighborhood: default=10
    The radius of circle that defines the neighnorhood of a node

    attribute_key: default:'occupancy'
    The key to attribute dictionary of the nodes to store the "occupancy"
    This method is used for measuring occupancy of nodes against occupancy map and maybe other image
    Therefor it is important to store the result in the atrribute dictionary with proper key


    Note
    ----
    "neighborhood_area" is only dependant on the "neighborhood" parameter.
    Hence it is the same for all nodes
    '''

    # constructing a point set corresponding to occupied pixels 
    occupied_pixels = np.fliplr( np.transpose(np.nonzero(image<occupancy_thr)) )
    
    # approximately the number of pixels in the neighborhood disk
    neighborhood_area = np.pi * neighborhood**2
    
    for key in arrangement.graph.node.keys():
        # coordinates of the node
        p = np.array([ float(arrangement.graph.node[key]['obj'].point.x),
                       float(arrangement.graph.node[key]['obj'].point.y) ])

        # distance between the node and every point in tthe point set
        distance = np.sqrt( np.sum((occupied_pixels - p)**2, axis=1) )

        # counting occupied pixels in the neighborhood 
        occupied_neighbors = len( np.nonzero(distance<neighborhood)[0] )

        # if neighbors.shape[0] is zero, I will face division by zero
        # when checking for occupancy ratio. this is actually a problem
        # for short edges, not point's neighhborhood. Unless stupidly I
        # set neighborhood =0!
        o = occupied_neighbors
        n = np.max([1,neighborhood_area])

        arrangement.graph.node[key]['obj'].attributes[attribute_key] = [o, n]

# ################################################################################
# def prune_arrangement_with_face_growing (arrangement, label_image,
#                                          low_occ_percent, # for edge to prun
#                                          high_occ_percent, # for edge to prun
#                                          consider_categories, # for edge to prun
#                                          similar_thr):
#     '''
#     For every neighboruing faces, merge if:
#     1. faces are neighboring with same place categies
#     2. the mutual edges are in the list `edges_to_purge`
#     3. the emerging face must have the same shape as initial faces

#     Note
#     ----
#     Very very experimental:
#     1) arr.merge_faces_on_fly() is not complete, see the method itself
#     2) stochastic merging of faces and the condition on rejecting the emerging
#     face if the shape does not match the original, would lead to cases where 
#     the merging would not resolve the over decomposition:
#     |x|x|x|
#     |x|x|x|
#     |x|x|x|
#     to:
#     |0 0|1|
#     |3 x|1|
#     |3|2 2|
     
#     '''

#     # be almost generous with this, not too much, this is like a green light
#     # the faces won't merge unless they have same category and same shape 
#     edges_to_purge = get_edges_to_purge (arrangement,
#                                          low_occ_percent=low_occ_percent,
#                                          high_occ_percent=high_occ_percent,
#                                          consider_categories=consider_categories )

#     # set shape attribute for all faces
#     for face in arrangement.decomposition.faces:
#         face.set_shape_descriptor(arrangement, remove_redundant_lines=True)    

#     done_growing = False
#     while not done_growing:
#         # unless a new pair of faces are merged, we assume we are done merging
#         done_growing = True

#         faces = arrangement.decomposition.faces
#         for (f1Idx,f2Idx) in itertools.combinations( range(len(faces) ), 2):
    
#             f1, f2 = faces[f1Idx], faces[f2Idx]
#             mut_he = arrangement.decomposition.find_mutual_halfEdges(f1Idx,f2Idx)                    
#             # checking if faces are similar (category label)
#             similar_label = are_same_category(f1,f2, thr=similar_thr)
            
#             # checking if faces are similar (shape)
#             similar_shape = True if len(utls.match_face_shape(f1,f2))>0 else False
            
#             # cheking if it's ok to prun mutual halfedges
#             ok_to_prun = all([he in edges_to_purge for he in mut_he])
            
#             if similar_label and similar_shape and ok_to_prun:
            
#                 new_face = arr.merge_faces_on_fly(arrangement, f1Idx, f2Idx)
#                 # new_face could be none if faces are not neighbors, or
#                 # if there are disjoint chains of halfedges 
#                 if new_face is not None:
                    
#                     # checking if the new face has similar shape to originals
#                     new_face.set_shape_descriptor(arrangement, remove_redundant_lines=True)
#                     if len(utls.match_face_shape(new_face,f1))>0:
#                         done_growing = False
#                         # Note: change of faces tuple messes up the indices
#                         # and the correspondance with con_map nodes
                        
#                         # setting label attributes of the new_face
#                         assign_label_to_face(label_image, new_face)
                        
#                         # updating the list of faces
#                         fcs = list(faces)
#                         fcs.pop(max([f1Idx, f2Idx]))
#                         fcs.pop(min([f1Idx, f2Idx]))
#                         fcs.append(new_face)
#                         arrangement.decomposition.faces = tuple(fcs)
                        
#                         # removing edges from the graph
#                         arrangement.graph.remove_edges_from(mut_he)
                        
#                         # since the tuple of faces is changed, start over
#                         break

#     # remove redundant nodes
#     arrangement.remove_nodes(nodes_idx=[], loose_degree=2)
#     return arrangement


################################################################################
def prune_arrangement( arrangement, image,
                       image_occupancy_thr = 200,
                       edge_neighborhood = 10,
                       node_neighborhood = 10,
                       low_occ_percent  = .025, # .005 # .01# .02 - below "low_occ_percent"
                       high_occ_percent = .1, # .050 # .03# .04 - not more than "high_occ_percent"
                       consider_categories = True
                   ): 
    '''
    category_forbidden
    It is passed to "get_edges_to_purge"
    Is category_forbidden is True, "forbidden_edges" in the "get_edges_to_purge"
    method will include, in addition to boundary edges, those edges in between
    two faces with different place category labels.  
    '''

    ### setting occupancy for nodes and edges
    set_node_occupancy(arrangement, image,
                       occupancy_thr=image_occupancy_thr,
                       neighborhood=node_neighborhood,
                       attribute_key='occupancy')

    set_edge_occupancy(arrangement, image,
                       occupancy_thr=image_occupancy_thr,
                       neighborhood=edge_neighborhood,
                       attribute_key='occupancy')

    ### prunning - source: occupancy         
    # edge purging:
    edges_to_purge = get_edges_to_purge (arrangement,
                                         low_occ_percent,
                                         high_occ_percent,
                                         consider_categories)
    arrangement.remove_edges(edges_to_purge, loose_degree=2)
    
    # node purging:
    nodes_to_prune = get_nodes_to_prune (arrangement,
                                         low_occ_percent, high_occ_percent)
    arrangement.remove_nodes(nodes_to_prune, loose_degree=2)
    
    return arrangement


################################################################################
def loader (png_name, n_categories=2):
    ''' Load files '''
    
    yaml_name = png_name[:-3] + 'yaml'
    skiz_name = png_name[:-4] + '_skiz.png'
    ply_name = png_name[:-3] + 'ply'
    label_name = png_name[:-4]+'_labels_km{:s}.npy'.format(str(n_categories))    
    dis_name = png_name[:-4] + '_dis.png'

    ### loading image and converting to binary 
    image = np.flipud( cv2.imread( png_name, cv2.IMREAD_GRAYSCALE) )
    thr1,thr2 = [200, 255]
    ret, image = cv2.threshold(image.astype(np.uint8) , thr1,thr2 , cv2.THRESH_BINARY)

    ### loading label_image
    label_image = np.load(label_name)

    ### loading distance image
    dis_image = np.flipud( cv2.imread(dis_name , cv2.IMREAD_GRAYSCALE) )

    ### laoding skiz image
    skiz = np.flipud( cv2.imread( skiz_name, cv2.IMREAD_GRAYSCALE) )    

    ### loading traits from yamls
    trait_data = utls.load_data_from_yaml( yaml_name )   
    traits = trait_data['traits']
    boundary = trait_data['boundary']
    boundary[0] -= 20
    boundary[1] -= 20
    boundary[2] += 20
    boundary[3] += 20

    ### trimming traits
    traits = utls.unbound_traits(traits)
    traits = utls.bound_traits(traits, boundary)

    return image, label_image, dis_image, skiz, traits




################################################################################
################################################# plotting stuff - not important
################################################################################

def plot_connectivity_map(axes, connectivity_map):
    X,Y = zip( *[ connectivity_map.node[key]['coordinate']
                  for key in connectivity_map.node.keys() ] )
    axes.plot(X,Y, 'go', alpha=.7)
    for (s,e,k) in connectivity_map.edges(keys=True):
        X,Y = zip( *[ connectivity_map.node[key]['coordinate']
                      for key in (s,e) ] )
        axes.plot(X,Y, 'g-', alpha=.7)
    
    return axes

########################################
def plot_image(axes, image, alpha=1., cmap='gray'):
    axes.imshow(image, cmap=cmap, alpha=alpha, interpolation='nearest', origin='lower')
    return axes

########################################
def plot_arrangement(axes, arrange, printLabels=False ):
    aplt.plot_edges (axes, arrange, alp=.1, col='b', printLabels=printLabels)
    aplt.plot_nodes (axes, arrange, alp=.5, col='r', printLabels=printLabels)
    return axes

################################################################################
def plot_text_edge_occupancy(axes, arrange):
    for s,e,k in arrange.graph.edges(keys=True):
        p1 = arrange.graph.node[s]['obj'].point
        p2 = arrange.graph.node[e]['obj'].point
        x, y = p1.x.evalf() , p1.y.evalf()
        dx, dy = p2.x.evalf()-x, p2.y.evalf()-y

        o,n = arrange.graph[s][e][k]['obj'].attributes['occupancy']

        axes.text( x+(dx/2), y+(dy/2), 
                   '{:.2f}'.format(float(o)/n),
                   fontdict={'color':'k',  'size': 10})


################################################################################
def plot_place_categories (axes, arrangement, alpha=.5):

    clrs = ['k', 'm', 'y', 'c', 'b', 'r', 'g']
    
    for face in arrangement.decomposition.faces:
        # face.attributes['label'] = [-1,0,...,5]
        clr = clrs [ int(face.attributes['label_vote']+1) ]    
        patch = mpatches.PathPatch(face.get_punched_path(),
                                   facecolor=clr, edgecolor=None,
                                   alpha=alpha)        
        axes.add_patch(patch)


########################################
def plot_node_edge_occupancy_statistics(arrange, bins=30):
    ''' '''
    edge_occ = np.array([ arrange.graph[s][e][k]['obj'].attributes['occupancy']
                          for (s,e,k) in arrange.graph.edges(keys=True) ]).astype(float)

    node_occ = np.array([ arrange.graph.node[key]['obj'].attributes['occupancy']
                          for key in arrange.graph.nodes() ]).astype(float)


    fig, axes = plt.subplots(2,2, figsize=(20,12))
    axes[0,0].set_title('edge occupancy')
    axes[0,0].plot(edge_occ[:,0], label='#occupied')
    axes[0,0].plot(edge_occ[:,1], label='#neighbors')
    axes[0,0].plot(edge_occ[:,0] / edge_occ[:,1], label='#o/#n')
    axes[0,0].legend(loc='upper right')    

    # axes[1,0].set_title('edge occupancy')
    axes[1,0].hist(edge_occ[:,0] / edge_occ[:,1], bins=bins)

    axes[0,1].set_title('node occupancy')
    axes[0,1].plot(node_occ[:,0], label='#occupied')
    axes[0,1].plot(node_occ[:,1], label='#neighbors')
    axes[0,1].plot(node_occ[:,0] / node_occ[:,1], label='#o/#n')
    axes[0,1].legend(loc='upper right')

    # axes[1,1].set_title('node occupancy')
    axes[1,1].hist(node_occ[:,0] / node_occ[:,1], bins=bins)
    
    plt.tight_layout()
    plt.show()


########################################
def plot_point_sets (src, dst=None):
    fig = plt.figure()
    fig.add_axes([0, 0, 1, 1])
    fig.axes[0].plot(src[:,0] ,  src[:,1], 'b.')
    if dst is not None:
        fig.axes[0].plot(dst[:,0] ,  dst[:,1], 'r.')
    fig.axes[0].axis('equal')
    # fig.show() # using fig.show() won't block the code!
    plt.show()

################################################################################
def visualize(X, Y, ax):
    '''
    This method is for the animation of CPD from:
    https://github.com/siavashk/Python-CPD

    X: destination
    Y: source
    '''

    plt.cla()
    ax.scatter(X[:,0] ,  X[:,1], color='red')
    ax.scatter(Y[:,0] ,  Y[:,1], color='blue')
    ax.axis('equal')
    plt.draw()
    plt.pause(0.01**5)


################################################################################
def plot_transformed_images(src, dst, tformM=None,
                            axes=None, title=None,
                            pts_to_draw=None ):
    '''
    src,dst (images 2darray)

    tformM (2darray 3x3 - optional)
    default (None) will use an identity matrix

    axes (matplotlib axes - optional)
    if axes is None, the method will plot everythnig self-contained
    otherwise, will plot over provided axes and will return axes

    title (string - optional)
    title for axes

    pts_to_draw (dictionary - optional)
    pts_to_draw['pts'] contains a point set to plot
    pts_to_draw['mrk'] is the marker (eg. 'r,', 'b.') for point plot
    if pts_to_draw['mrk'] is not provided, marker is set to 'r,'

    '''

    aff2d = matplotlib.transforms.Affine2D( tformM )
    # aff2d._mtx == tformM

    return_axes = True
    if axes is None:
        return_axes = False
        fig, axes = plt.subplots(1,1, figsize=(20,12))

    # drawing images and transforming src image
    im_dst = axes.imshow(dst, origin='lower', cmap='gray', alpha=.5, clip_on=True)
    im_src = axes.imshow(src, origin='lower', cmap='gray', alpha=.5, clip_on=True)
    im_src.set_transform( aff2d + axes.transData )

    # finding the extent of of dst and transformed src
    xmin_d,xmax_d, ymin_d,ymax_d = im_dst.get_extent()
    x1, x2, y1, y2 = im_src.get_extent()
    pts = [[x1,y1], [x2,y1], [x2,y2], [x1,y1]]
    pts_tfrom = aff2d.transform(pts)    

    xmin_s, xmax_s = np.min(pts_tfrom[:,0]), np.max(pts_tfrom[:,0]) 
    ymin_s, ymax_s = np.min(pts_tfrom[:,1]), np.max(pts_tfrom[:,1])

    # setting the limits of axis to the extents of images
    axes.set_xlim( min(xmin_s,xmin_d), max(xmax_s,xmax_d) )
    axes.set_ylim( min(ymin_s,ymin_d), max(ymax_s,ymax_d) )

    if pts_to_draw is not None:
        pts = pts_to_draw['pts']
        mrk = pts_to_draw['mrk'] if 'mrk' in pts_to_draw else 'r,'
        axes.plot(pts[:,0], pts[:,1], mrk)

    # # turn off tickes
    # axes.set_xticks([])
    # axes.set_yticks([])

    if title is not None: axes.set_title(title)

    if return_axes:
        return axes
    else:
        plt.tight_layout()
        plt.show()


################################################################################
def histogram_of_face_category_distances(arrangement):
    '''
    this method plots the histogram of face category distance (face.attributes['label_count'])
    
    Blue histogram:
    distances between those faces that are assigned with same category in voting (face.attributes['label_vote'])

    Red hsitogram:
    distances between those faces that are assigned with differnt categories in voting (face.attributes['label_vote'])

    '''
    same_lbl_dis = []
    diff_lbl_dis = []
    for (f1,f2) in itertools.combinations( arrangement.decomposition.faces, 2):
    
        dis = face_category_distance(f1,f2)

        if f1.attributes['label_vote'] == f2.attributes['label_vote']:
            same_lbl_dis += [dis]
        else:
            diff_lbl_dis += [dis]
    
    fig, axes = plt.subplots(1,1, figsize=(20,12))
    h_same = axes.hist(same_lbl_dis, facecolor='b', bins=30, alpha=0.7, label='same category')
    h_diff = axes.hist(diff_lbl_dis, facecolor='r', bins=30, alpha=0.7, label='diff category')

    axes.legend(loc=1, ncol=1)
    axes.set_title('histogram of face category distance')
    plt.tight_layout()
    plt.show()


################################################################################
def histogram_of_alignment_parameters(parameters):
    '''
    '''    
    fig, axes = plt.subplots(1,1, figsize=(20,12))
    axes.hist(parameters[:,0], facecolor='b', bins=1000, alpha=0.7, label='tx')
    axes.hist(parameters[:,1], facecolor='r', bins=1000, alpha=0.7, label='ty')
    axes.hist(parameters[:,2], facecolor='g', bins=1000, alpha=0.7, label='rotate')
    axes.hist(parameters[:,3], facecolor='m', bins=1000, alpha=0.7, label='scale')

    axes.legend(loc=1, ncol=1)
    axes.set_title('histogram of alignment parameters')
    plt.tight_layout()
    plt.show()


################################################################################
def plot_face2face_association_match_score(arrange_src, arrange_dst,
                                           f2f_association, f2f_match_score):

    ### fetch the center of faces
    face_cen_src = np.array([face.attributes['centre']
                             for face in arrange_src.decomposition.faces])
    face_cen_dst = np.array([face.attributes['centre']
                             for face in arrange_dst.decomposition.faces])

    fig, axes = plt.subplots(1, 1, figsize=(20,12))

    ### source : blue
    aplt.plot_edges (axes, arrange_src, alp=.3, col='b', printLabels=False)
    axes.plot(face_cen_src[:,0], face_cen_src[:,1], 'b*', alpha=.5)

    ### destination : green
    aplt.plot_edges (axes, arrange_dst, alp=.3, col='g', printLabels=False)
    axes.plot(face_cen_dst[:,0], face_cen_dst[:,1], 'g*', alpha=.5)

    ### face to face association and match score
    for src_idx in f2f_association.keys():
        dst_idx = f2f_association[src_idx]
        x1,y1 = face_cen_src[ src_idx ]
        x2,y2 = face_cen_dst[ dst_idx ]
        # plot association
        axes.plot([x1,x2], [y1,y2], 'r', alpha=.5)
        # print match score
        score = f2f_match_score[(src_idx,dst_idx)]
        axes.text(np.mean([x1,x2]) , np.mean([y1,y2]),
                  str(score), fontdict={'color':'k',  'size': 10})

    axes.axis('equal')
    plt.tight_layout()
    plt.show()
