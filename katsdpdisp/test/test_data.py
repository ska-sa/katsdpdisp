"""Tests for :py:mod:`katsdpdisp.data`."""

import numpy as np
from numpy.testing import assert_array_equal
from katsdpdisp.data import SparseArray

def test_sparsearray(fullslots=100,fullbls=10,fullchan=5,nslots=10,maxbaselines=6,islot_new_bls=6):
    """Simulates the assignment and retrieval of data as it happens in the signal displays when 
    it receives different sets of baseline data at different timestamps, with some time continuity.
    (fullslots,fullbls,fullchan) is the dimensions of the full/complete dataset
    (nslots,maxbaselines,fullchan) is the true size of the sparse array, representing a size of (nslots,fullbls,fullchan)
    where maxbaselines<fullbls
    islot_new_bls is the number of time stamps that passes before there is a new baseline product selected/chosen in the test sequence"""
    mx=SparseArray(nslots,fullbls,fullchan,maxbaselines,dtype=np.int32)

    rs = np.random.RandomState(seed=0)
    fulldata=rs.random_integers(0,10,[fullslots,fullbls,fullchan])
    histbaselines=[]
    for it in range(fullslots):
        if it%islot_new_bls==0:#add a new baseline, remove old, every so often
            while True:
                newbaseline=rs.random_integers(0,fullbls-1,[1])
                if len(histbaselines)==0 or (newbaseline not in histbaselines[-1]):
                    break
            if (len(histbaselines)==0):
                newbaselines=np.r_[newbaseline]
            elif (len(histbaselines[-1])<islot_new_bls):
                newbaselines=np.r_[histbaselines[-1],newbaseline]
            else:
                newbaselines=np.r_[histbaselines[-1][1:],newbaseline]
        histbaselines.append(newbaselines)
        mx[it%nslots,histbaselines[-1],:]=fulldata[it,histbaselines[-1],:]
        for cit in range(islot_new_bls):
            if (cit>=len(histbaselines)):
                break
            hasthesebaselines=list(set(histbaselines[-1-cit]) & set(histbaselines[-1]))
            missingbaselines=list(set(histbaselines[-1-cit]) - set(histbaselines[-1]))
            retrieved=mx[(it-cit)%nslots,hasthesebaselines,:]
            assert_array_equal(retrieved, fulldata[it-cit,hasthesebaselines,:], 'SparseArray getitem test failed')
            missingretrieved=mx[(it-cit)%nslots,missingbaselines,:]
            assert_array_equal(missingretrieved,np.zeros(missingretrieved.shape,dtype=np.int32), 'SparseArray missing baseline test failed')

def test_sparsearray_indexing(fullslots=100,fullbls=10,fullchan=5,nslots=10,maxbaselines=6):
    mx=SparseArray(nslots,fullbls,fullchan,maxbaselines,dtype=np.int32)

    rs = np.random.RandomState(seed=0)
    fulldata=rs.random_integers(0,10,[fullslots,fullbls,fullchan])

    mx[0,0,0]=fulldata[0,0,0]
    assert_array_equal(mx[0,0,0], fulldata[0,0,0], 'SparseArray [scalar,scalar,scalar] index test failed')

    mx[1,1,:]=fulldata[1,1,:]
    assert_array_equal(mx[1,1,:], fulldata[1,1,:], 'SparseArray [scalar,scalar,slice] index test 2 failed') #baseline change so previous assignment purged (in future may retain until running out of memory and necessary to purge)

    mx[2,1,:]=fulldata[2,1,:]
    assert_array_equal(mx[1:3,1,:], fulldata[1:3,1,:], 'SparseArray retain old value test failed') #assign to same baseline so previous slot value remain

    mx[3,:maxbaselines,0]=fulldata[3,:maxbaselines,0]
    assert_array_equal(mx[3,:maxbaselines,0], fulldata[3,:maxbaselines,0], 'SparseArray [scalar,slice,scalar] index test failed')

    mx[:,1,3]=fulldata[:nslots,1,3]
    assert_array_equal(mx[:,1,3], fulldata[:nslots,1,3], 'SparseArray [slice,scalar,scalar] index test failed')
    
    mx[:,1,:]=fulldata[:nslots,1,:]
    assert_array_equal(mx[:,1,:], fulldata[:nslots,1,:], 'SparseArray [slice,scalar,slice] index test failed')

    mx[:,1:maxbaselines,:]=fulldata[2:nslots+2,1:maxbaselines,:]
    assert_array_equal(mx[:,1:maxbaselines,:], fulldata[2:nslots+2,1:maxbaselines,:], 'SparseArray [slice,slice,slice] index test failed')

