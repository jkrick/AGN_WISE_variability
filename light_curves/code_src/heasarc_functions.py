import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyvo
from tqdm import tqdm

from data_structures import MultiIndexDFObject
from sample_selection import make_coordsTable


#need to know the distribution of error radii for the catalogs of interest
#this will inform the ligh curve query, as we are not interested in 
#error radii which are 'too large' so we need a way of defining what that is.
#leaving this code here in case user wants to change the cutoff error radii 
#based on their science goals.  It is not currently used anywhere in the code
def make_hist_error_radii(missioncat):
    """plots a histogram of error radii from a HEASARC catalog
   
    example calling sequences:
    resulttable = make_hist_error_radii('FERMIGTRIG')
    resulttable = make_hist_error_radii('SAXGRBMGRB')


    Parameters
    ----------
    missioncat : str 
        single catalog within HEASARC to grab error radii values  Must be one of the catalogs listed here: 
            https://astroquery.readthedocs.io/en/latest/heasarc/heasarc.html#getting-list-of-available-missions
    Returns
    -------
    heasarcresulttable : astropy table
        results of the heasarc search including name, ra, dec, error_radius
        
    """
    # get the pyvo HEASARC service.
    heasarc_tap = pyvo.regsearch(servicetype='tap',keywords=['heasarc'])[0]

    #simple query to select sources from that catalog
    heasarcquery=f"""
        SELECT TOP 5000 cat.name, cat.ra, cat.dec, cat.error_radius
        FROM {missioncat} as cat
         """
    heasarcresult = heasarc_tap.service.run_sync(heasarcquery)

    #  Convert the result to an Astropy Table
    heasarcresulttable = heasarcresult.to_table()

    #make a histogram
    #zoom in on the range of interest
    #error radii are in units of degrees
    plt.hist(heasarcresulttable["error_radius"], bins = 30, range = [0, 10])
    
    #in case anyone wants to look further at the data
    return heasarcresulttable
    

def HEASARC_get_lightcurves(source_table, heasarc_cat, max_error_radius):
    """Searches HEASARC archive for light curves from a specific list of mission catalogs
    
    Parameters
    ----------
    source_table : `~astropy.table.Table`
        Table with the coordinates and journal reference labels of the sources
    heasarc_cat : str list
        list of catalogs within HEASARC to search for light curves.  Must be one of the catalogs listed here: 
            https://astroquery.readthedocs.io/en/latest/heasarc/heasarc.html#getting-list-of-available-missions
    max_error_radius : flt list
        maximum error radius to include in the returned catalog of objects 
        ie., we are not interested in GRBs with a 90degree error radius because they will fit all of our objects
    xmlfilename: str
        filename which has the list of sources to cross match with HEASARC catalogs
        must be  a VOTable in xml format
        generated by `make_VOTable` functiom
        
    Returns
    -------
    df_lc : MultiIndexDFObject
        the main data structure to store all light curves
    """

    # Prepping source_table with float R.A. and DEC column instead of SkyCoord mixin for TAP upload

    upload_table = source_table['object_id', 'label']
    upload_table['ra'] = source_table['coord'].ra.deg
    upload_table['dec'] = source_table['coord'].dec.deg

    #setup to store the data
    df_lc = MultiIndexDFObject()

    # get the pyvo HEASARC service.
    heasarc_tap = pyvo.regsearch(servicetype='tap', keywords=['heasarc'])[0]

    # Note that the astropy table is uploaded when we run the query with run_sync
    for m in tqdm(range(len(heasarc_cat))):    
        print('working on mission', heasarc_cat[m])
        
        hquery = f"""
            SELECT cat.name, cat.ra, cat.dec, cat.error_radius, cat.time, mt.object_ID, mt.label
            FROM {heasarc_cat[m]} cat, tap_upload.mytable mt
            WHERE
            cat.error_radius < {max_error_radius[m]} AND
            CONTAINS(POINT('ICRS',mt.ra,mt.dec),CIRCLE('ICRS',cat.ra,cat.dec,cat.error_radius))=1
             """
        
        hresult = heasarc_tap.service.run_sync(hquery, uploads={'mytable': upload_table})
        print(f'length of {heasarc_cat[m]} catalog:', len(hresult))

        #  Convert the result to an Astropy Table
        hresulttable = hresult.to_table()

        #add results to multiindex_df
        #really just need to mark this spot with a vertical line in the plot, it's not actually a light curve
        #so making up a flux and an error, but the time stamp and mission are the real variables we want to keep
        df_heasarc = pd.DataFrame(dict(flux=np.full(len(hresulttable), 0.1), err=np.full(len(hresulttable), 0.1),
                                       time=hresulttable['time'], object_id=hresulttable['object_id'],
                                       band=np.full(len(hresulttable), heasarc_cat[m]),
                                       label=hresulttable['label'])).set_index(["object_id", "label", "band", "time"])

        # Append to existing MultiIndex light curve object
        df_lc.append(df_heasarc)
    
    return df_lc

