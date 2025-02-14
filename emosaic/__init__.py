import time
import traceback
import random

import numpy as np
import cv2

from emosaic.utils.image import divide_image_rectangularly, to_vector


def mosaicify(
        target_image, 
        tile_h, tile_w, 
        tile_index,
        tile_images,
        verbose=1,
        use_stabilization=False,
        stabilization_threshold=0.95,
        randomness=0.0,
        opacity=0.0,
        best_k=1,
        trim=True,
        uniform_k=True,
        no_duplicates_radius=0,
        no_duplicates=True,
    ):
    try:
        rect_starts = divide_image_rectangularly(target_image, h_pixels=tile_h, w_pixels=tile_w)

        indexes = {(coord[0]/tile_h, coord[1]/tile_w): None for coord in rect_starts}
        max_ix = max([coord[0] for coord in indexes.keys()])
        max_iy = max([coord[1] for coord in indexes.keys()])
        # if verbose:
        #     print("no_duplicates_radius: " + str(no_duplicates_radius))
        #     print("indexes: " + str(indexes))
        #     print("(max_x, max_y)): " + str((max_ix, max_iy)))

        mosaic = np.zeros(target_image.shape)

        if use_stabilization:
            dist_shape = (target_image.shape[0], target_image.shape[1])
            last_dist = np.zeros(dist_shape).astype(np.int32)
            last_dist[:, :] = 2**31 - 1

        timings = []
        if verbose:
            print("We have %d tiles to assign" % len(rect_starts))

        seen_idx = { -1 }
        for (j, (x, y)) in enumerate(rect_starts):
            starttime = time.time()

            ix, iy = x / tile_h, y / tile_w
            
            # get our target region & vectorize it
            target = target_image[x : x + tile_h, y : y + tile_w]
            target_h, target_w, _ = target.shape
            v = to_vector(target, tile_h, tile_w)
            
            # find nearest codebook image
            try:
                while True:

                    if best_k == 1:
                        dist, I = tile_index.search(v, k=1)
                        idx = I[0][0]
                    elif uniform_k:
                        dist, I = tile_index.search(v, k=best_k)
                        idx = random.choice(I[0])
                    else:
                        dist, I = tile_index.search(v, k=best_k + 1)
                        distances = dist[0]
                        deviation_from_max = np.abs(distances - distances.max())
                        weighting = deviation_from_max / deviation_from_max.sum()
                        idx = np.random.choice(I[0], p=weighting)

                    # if verbose:
                    #     print("(j, x, y): " + str((j, x, y)))
                    #     print("idx: %d" % idx)
                    #     print("Checked indexes: " + str([
                    #         (a, b, indexes[(a, b)])
                    #         for a in range(max(0, ix-no_duplicates_radius), min(max_ix, ix+no_duplicates_radius))
                    #         for b in range(max(0, iy-no_duplicates_radius), min(max_iy, iy+no_duplicates_radius))
                    #     ]))
                    if no_duplicates_radius > 0 and any([
                        idx == indexes[(a, b)]
                        for a in range(max(0, ix-no_duplicates_radius), min(max_ix, ix+no_duplicates_radius))
                        for b in range(max(0, iy-no_duplicates_radius), min(max_iy, iy+no_duplicates_radius))
                        if a**2 + b**2 <= no_duplicates_radius**2
                    ]):
                        best_k += 1
                    else:
                        break

                closest_tile = tile_images[idx]
                indexes[(ix, iy)] = idx
            except Exception:
                import ipdb; ipdb.set_trace()
            
            # write into mosaic
            if random.random() < randomness:
                # pick a random tile!
                num_images = len(tile_images)
                rand_idx = random.choice(range(num_images))
                if rand_idx in seen_idx:
                    remaining_idx = set(range(num_images)) - seen_idx
                    try:
                        rand_idx = random.choice(list(remaining_idx))
                    except IndexError:
                        # just pick one anyway
                        rand_idx = random.choice(range(num_images))

                seen_idx.add(rand_idx)
                mosaic[x : x + tile_h, y : y + tile_w] = tile_images[rand_idx]
            else:
                if use_stabilization:
                    if dist < last_dist[x, y] * stabilization_threshold:
                        mosaic[x : x + tile_h, y : y + tile_w] = closest_tile
                else:
                    mosaic[x : x + tile_h, y : y + tile_w] = closest_tile

            # set new last dist
            if use_stabilization:
                last_dist[x, y] = dist
            
            # record the performance
            elapsed = time.time() - starttime
            timings.append(elapsed)

        # print("indexes: " + str(indexes))

        # should we adjust opacity? 
        if opacity > 0:
            mosaic = cv2.addWeighted(target_image, opacity, mosaic.astype(np.uint8), 1 - opacity, 0)
        else:
            mosaic = mosaic.astype(np.uint8)

        # should we trim the image to only the tiled area?
        if trim:
            (x1, y1), (x2, y2) = rect_starts[0], rect_starts[-1]
            mosaic = mosaic[x1 : x2, y1 : y2]
            
        # show some results
        arr = np.array(timings)
        if verbose:
            print("Timings: mean=%.5f, stddev=%.5f" % (arr.mean(), arr.std()))
        return mosaic, rect_starts, arr

    except Exception:
        print(traceback.format_exc())
        import ipdb; ipdb.set_trace()
        return None, None, None
