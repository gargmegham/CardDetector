import json
import cv2, time
import numpy as np
import pandas as pd
from difflib import SequenceMatcher
 
#from config import Config
 
from .task_executor import TaskExecutor
from .p_hash import pHash
from . import utils
 
def find_rects_in_image(img, thresh_c=5, kernel_size=(3, 3), size_thresh=10000):
    """
    Find contours of all cards in the image
    :param img: source image
    :param thresh_c: value of the constant C for adaptive thresholding
    :param kernel_size: dimension of the kernel used for dilation and erosion
    :param size_thresh: threshold for size (in pixel) of the contour to be a candidate
    :return: list of candidate contours
    """
    # Typical pre-processing - grayscale, blurring, thresholding
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
 
    # clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    # img_clahe = clahe.apply(img_gray)
 
    img_blur = cv2.medianBlur(img_gray, 5)
    img_thresh = cv2.adaptiveThreshold(img_blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 5, thresh_c)
 
    # Dilute the image, then erode them to remove minor noises
    kernel = np.ones(kernel_size, np.uint8)
    img_dilate = cv2.dilate(img_thresh, kernel, iterations=1)
    img_erode = cv2.erode(img_dilate, kernel, iterations=1)
 
    # Find the contour
    cnts, hier = cv2.findContours(img_erode, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if len(cnts) == 0:
        #print('no contours')
        return []
 
    # The hierarchy from cv2.findContours() is similar to a tree: each node has an access to the parent, the first child
    # their previous and next node
    # Using recursive search, find the uppermost contour in the hierarchy that satisfies the condition
    # The candidate contour must be rectangle (has 4 points) and should be larger than a threshold
    cnts_rect = []
    stack = [ (0, hier[0][0]) ]
    while len(stack) > 0:
        i_cnt, h = stack.pop()
        i_next, i_prev, i_child, i_parent = h
        if i_next != -1:
            stack.append((i_next, hier[0][i_next]))
        cnt = cnts[i_cnt]
        size = cv2.contourArea(cnt)
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if size >= size_thresh and len(approx) == 4:
            cnts_rect.append(approx)
        else:
            if i_child != -1:
                stack.append((i_child, hier[0][i_child]))
    return cnts_rect
 
def detect_image(img, card_dict, phash_cnt, current_cards, size_thresh=10000):
    """
    Identify all cards in the input frame\n
    ---
    :param img: cv2 input image
    :param card_pool: pandas dataframe of all card's information
    :param hash_size: param for pHash algorithm
    :param size_thresh: threshold for size (in pixel) of the contour to be a candidate
    :param out_path: path to save the result
    :param display: flag for displaying the result
    :param debug: flag for debug mode
    :return: list of detected card's name/set and resulting image
    """
    try:
        img_result = img.copy() # For displaying and saving
    except:
        return img
    det_cards = []
    cnts = find_rects_in_image(img_result, size_thresh=size_thresh)
    for (i,cnt) in enumerate(cnts):
        pts = utils.cnt_to_pts(cnt)
        img_warp = utils.four_point_transform(img, pts)
        phash_value = pHash.img_to_phash(img_warp, crop_scale=0.95, hash_size=8)
        phash_value = "".join(phash_value.astype("int8").astype(str))
        phash_value = "{0:0>4X}".format(int(phash_value, 2))
        det_cards += [{
                        "phash":phash_value,
                        "cnt":cnt
        }]
        FILL_COLOR = (60, 120, 170)[::-1] # as BGR
        for d in det_cards:
            pts = utils.cnt_to_pts(d['cnt'])
            rect_image = np.zeros_like(img_result)

            cv2.drawContours(rect_image, [d['cnt']], -1, FILL_COLOR, -1, cv2.LINE_AA)

            cv2.putText(img_result, str(d['phash']), (int(min(pts[0][0], pts[1][0])), int(min(pts[0][1], pts[1][1]))),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)
            img_result = cv2.addWeighted(img_result, 1, rect_image, 0.75, 0)
    for card in det_cards:
        found = False
        # check for similarity to any current card
        for old_card_key in [k for k, v in sorted(card_dict.items(), key=lambda item: item[1])[::-1]]:
            if SequenceMatcher(None, card["phash"], old_card_key).ratio() >= 0.65:
                # if high match, increment old
                card_dict[old_card_key] += 1
                phash_cnt[old_card_key] = card["cnt"]
                found = True
                break
        if not found:
            # add new element to the dict
            card_dict[card["phash"]] = 1
            phash_cnt[card["phash"]] = card["cnt"]
 
    for old_card_key in card_dict.keys():
        if old_card_key not in [e["phash"] for e in det_cards]:
            # decrement qty
            card_dict[old_card_key] = np.max([1, card_dict[old_card_key]-.75])

    confident_cards = []
    for card_key in card_dict.keys():
        if card_dict[card_key] >= 3:
            confident_cards.append([card_key, phash_cnt[card_key]])
    cards_present = {}
    new_current_cards = []
    for phash, cnt in confident_cards:
        if phash not in current_cards:
            cnt = cnt.reshape(4, 2)
            crop_img = utils.four_point_transform(img, cnt)
            cards_present[str(phash)] = utils.four_point_transform(img, cnt.reshape(4, 2))
        new_current_cards.append(phash)
    current_cards = new_current_cards
    return img_result, det_cards, card_dict, phash_cnt, current_cards, cards_present