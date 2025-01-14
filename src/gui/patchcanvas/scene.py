#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# PatchBay Canvas engine using QGraphicsView/Scene
# Copyright (C) 2010-2019 Filipe Coelho <falktx@falktx.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of
# the License, or any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# For a full copy of the GNU General Public License see the doc/GPL.txt file.

# ------------------------------------------------------------------------------------------------------------
# Imports (Global)

from math import floor
import time

from PyQt5.QtCore import (QT_VERSION, pyqtSignal, pyqtSlot, qFatal,
                          Qt, QPoint, QPointF, QRectF, QTimer, QSizeF, QMarginsF)
from PyQt5.QtGui import QCursor, QPixmap, QPolygonF, QLinearGradient, QColor
from PyQt5.QtWidgets import (QGraphicsRectItem, QGraphicsScene, QGraphicsView,
                             QApplication)

# ------------------------------------------------------------------------------------------------------------
# Imports (Custom)

from . import (
    canvas,
    options,
    CanvasBoxType,
    CanvasIconType,
    CanvasPortType,
    CanvasPortGroupType,
    CanvasLineType,
    CanvasBezierLineType,
    CanvasRubberbandType,
    ACTION_BG_RIGHT_CLICK,
    ACTION_DOUBLE_CLICK,
    MAX_PLUGIN_ID_ALLOWED,
    PORT_MODE_INPUT,
    PORT_MODE_OUTPUT,
    DIRECTION_NONE,
    DIRECTION_LEFT,
    DIRECTION_RIGHT,
    DIRECTION_UP,
    DIRECTION_DOWN
)

from .canvasbox import CanvasBox

# ------------------------------------------------------------------------------------------------------------

class RubberbandRect(QGraphicsRectItem):
    def __init__(self, scene):
        QGraphicsRectItem.__init__(self, QRectF(0, 0, 0, 0))

        self.setZValue(-1)
        self.hide()

        scene.addItem(self)

    def type(self):
        return CanvasRubberbandType

# ------------------------------------------------------------------------------------------------------------

class PatchScene(QGraphicsScene):
    scaleChanged = pyqtSignal(float)
    sceneGroupMoved = pyqtSignal(int, int, QPointF)
    pluginSelected = pyqtSignal(list)

    def __init__(self, parent, view):
        QGraphicsScene.__init__(self, parent)

        #self.setItemIndexMethod(QGraphicsScene.NoIndex)
        self.m_scale_area = False
        self.m_mouse_down_init = False
        self.m_mouse_rubberband = False
        self.m_mid_button_down = False
        self.m_pointer_border = QRectF(0.0, 0.0, 1.0, 1.0)
        self.m_scale_min = 0.1
        self.m_scale_max = 4.0

        self.scales = (0.1, 0.25, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0)

        self.m_rubberband = RubberbandRect(self)
        self.m_rubberband_selection = False
        self.m_rubberband_orig_point = QPointF(0, 0)

        self.m_view = view
        if not self.m_view:
            qFatal("PatchCanvas::PatchScene() - invalid view")

        self.curCut = None
        self.curZoomArea = None

        self._move_timer_start_at = 0
        self._move_timer_interval = 20 # 20 ms step animation (50 Hz)
        self.move_boxes = []
        self.wrapping_boxes = []
        self.move_box_timer = QTimer()
        self.move_box_timer.setInterval(self._move_timer_interval)
        self.move_box_timer.timeout.connect(self.move_boxes_animation)
        self.move_box_n = 0
        self.move_box_n_max = 16 # 16 animations steps (20ms * 16 = 320ms)
        

        self.elastic_scene = True
        self.resizing_scene = False

        self.selectionChanged.connect(self.slot_selectionChanged)
        
        self._prevent_overlap = True
        
        self.loading_items = False

    def clear(self):
        # reimplement Qt function and fix missing rubberband after clear
        QGraphicsScene.clear(self)
        self.m_rubberband = RubberbandRect(self)
        self.updateTheme()

    def getDevicePixelRatioF(self):
        if QT_VERSION < 0x50600:
            return 1.0

        return self.m_view.devicePixelRatioF()

    def getScaleFactor(self):
        return self.m_view.transform().m11()

    def fixScaleFactor(self, transform=None):
        fix, set_view = False, False
        if not transform:
            set_view = True
            view = self.m_view
            transform = view.transform()

        scale = transform.m11()
        if scale > self.m_scale_max:
            fix = True
            transform.reset()
            transform.scale(self.m_scale_max, self.m_scale_max)
        elif scale < self.m_scale_min:
            fix = True
            transform.reset()
            transform.scale(self.m_scale_min, self.m_scale_min)

        if set_view:
            if fix:
                view.setTransform(transform)
            self.scaleChanged.emit(transform.m11())

        return fix

    def fix_temporary_scroll_bars(self):
        if self.m_view is None:
            return

        if self.m_view.horizontalScrollBar().isVisible():
            self.m_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        else:
            self.m_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        if self.m_view.verticalScrollBar().isVisible():
            self.m_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        else:
            self.m_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def reset_scroll_bars(self):
        self.m_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.m_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def move_boxes_animation(self):
        # animation is nice but not the priority
        # do not ensure all steps are played
        # but just move the box where it has to go
        self.move_box_n = int((time.time() - self._move_timer_start_at)
                              / (self._move_timer_interval * 0.001))
        self.move_box_n = min(self.move_box_n, self.move_box_n_max)

        for box_dict in self.move_boxes:
            if box_dict['widget'] is not None:
                total_n = self.move_box_n_max - box_dict['n_start']
                n = self.move_box_n - box_dict['n_start']

                x = box_dict['from_x'] \
                    + (box_dict['to_x'] - box_dict['from_x']) \
                        * ((n/total_n) ** 0.6)
                y = box_dict['from_y'] \
                    + (box_dict['to_y'] - box_dict['from_y']) \
                        * ((n/total_n) ** 0.6)

                box_dict['widget'].setPos(x, y)

        for wrap_dict in self.wrapping_boxes:
            if wrap_dict['widget'] is not None:
                if self.move_box_n == self.move_box_n_max:
                    wrap_dict['widget'].animate_wrapping(1.00)
                else:
                    wrap_dict['widget'].animate_wrapping(
                        float(self.move_box_n / self.move_box_n_max))

        self.resize_the_scene()

        if self.move_box_n >= self.move_box_n_max:
            self.move_box_n = 0
            self.move_box_timer.stop()
            
            move_box_widgets = [b['widget'] for b in self.move_boxes]
            self.move_boxes.clear()
            self.wrapping_boxes.clear()
            QTimer.singleShot(0, self.update)

            for box_dict in self.move_boxes:
                if box_dict['widget'] is not None:
                    QTimer.singleShot(0, box_dict['widget'].repaintLines)
                    
            for box in move_box_widgets:
                if box is not None:
                    box.updatePositions()
                    box.send_move_callback()

            canvas.qobject.move_boxes_finished.emit()

        elif self.move_box_n % 5 == 4:
            self.update()

    def add_box_to_animation(self, box_widget, to_x: int, to_y: int,
                             force_anim=True):
        for box_dict in self.move_boxes:
            if box_dict['widget'] == box_widget:
                break
        else:
            if not force_anim:
                # if box is not in a current animation
                # and force_anim is False,
                # then box position is directly changed
                if box_widget is not None:
                    box_widget.setPos(int(to_x), int(to_y))
                return

            box_dict = {'widget': box_widget}
            self.move_boxes.append(box_dict)

        box_dict['from_x'] = box_widget.pos().x()
        box_dict['from_y'] = box_widget.pos().y()
        box_dict['to_x'] = int(to_x)
        box_dict['to_y'] = int(to_y)
        box_dict['n_start'] = self.move_box_n

        if not self.move_box_timer.isActive():
            self._move_timer_start_at = time.time()
            self.move_box_timer.start()

    def add_box_to_animation_wrapping(self, box_widget, wrap: bool):
        for wrap_dict in self.wrapping_boxes:
            if wrap_dict['widget'] == box_widget:
                wrap_dict['wrap'] = wrap
                break
        else:
            self.wrapping_boxes.append({'widget': box_widget, 'wrap': wrap})
        
        if not self.move_box_timer.isActive():
            self._move_timer_start_at = time.time()
            self.move_box_timer.start()

    def deplace_boxes_from_repulsers(self, repulser_boxes: list,
                                     wanted_direction=DIRECTION_NONE,
                                     new_scene_rect=None):
        if not options.prevent_overlap:
            return
        
        box_spacing = canvas.theme.box_spacing
        box_spacing_hor = canvas.theme.box_spacing_hor
        magnet = canvas.theme.magnet
        
        def get_direction(fixed_rect, moving_rect, parent_directions=[])->int:
            if (moving_rect.top() <= fixed_rect.center().y() <= moving_rect.bottom()
                    or fixed_rect.top() <= moving_rect.center().y() <= fixed_rect.bottom()):
                if (fixed_rect.right() < moving_rect.center().x()
                        and fixed_rect.center().x() < moving_rect.left()):
                    if DIRECTION_LEFT in parent_directions:
                        return DIRECTION_LEFT
                    return DIRECTION_RIGHT
                
                if (fixed_rect.left() > moving_rect.center().x()
                        and fixed_rect.center().x() > moving_rect.right()):
                    if DIRECTION_RIGHT in parent_directions:
                        return DIRECTION_RIGHT
                    return DIRECTION_LEFT
            
            if fixed_rect.center().y() <= moving_rect.center().y():
                if DIRECTION_UP in parent_directions:
                    return DIRECTION_UP
                return DIRECTION_DOWN
            
            if DIRECTION_DOWN in parent_directions:
                return DIRECTION_DOWN
            return DIRECTION_UP
        
        def repulse(direction: int, fixed, moving,
                    fixed_port_mode: int, moving_port_mode: int):
            ''' returns a qrect to be placed at side of fixed_rect
                where fixed_rect is an already determinated futur place
                for a box '''
                
            if isinstance(fixed, CanvasBox):
                fixed_rect = fixed.boundingRect().translated(fixed.pos())
            else:
                fixed_rect = fixed
            
            if isinstance(moving, CanvasBox):
                rect = moving.boundingRect().translated(moving.pos())
            else:
                rect = moving

            assert direction in (DIRECTION_DOWN, DIRECTION_LEFT,
                                 DIRECTION_UP, DIRECTION_RIGHT)
            
            x = rect.left()
            y = rect.top()
            
            if direction in (DIRECTION_LEFT, DIRECTION_RIGHT):
                spacing = box_spacing

                if direction == DIRECTION_LEFT:
                    if (fixed_port_mode & PORT_MODE_INPUT
                            or moving_port_mode & PORT_MODE_OUTPUT):
                        spacing = box_spacing_hor
                    x = fixed_rect.left() - spacing - rect.width()
                    if x < 0:
                        x -= 1.0
                    x = float(int(x))
                else:
                    if (fixed_port_mode & PORT_MODE_OUTPUT
                            or moving_port_mode & PORT_MODE_INPUT):
                        spacing = box_spacing_hor
                    x = fixed_rect.right() + spacing
                    if x < 0:
                        x -= 1.0
                    x = float(int(x + 0.99))

                top_diff = abs(fixed_rect.top() - rect.top())
                bottom_diff = abs(fixed_rect.bottom() - rect.bottom())

                if bottom_diff > top_diff and top_diff <= magnet:
                    y = fixed_rect.top()
                elif bottom_diff <= magnet:
                    y = fixed_rect.bottom() - rect.height()
            
            elif direction in (DIRECTION_UP, DIRECTION_DOWN):
                if direction == DIRECTION_UP:
                    y = fixed_rect.top() - box_spacing - rect.height()
                    if y < 0:
                        y -= 1.0
                    y = float(int(y))
                else:
                    y = fixed_rect.bottom() + box_spacing
                    if y < 0:
                        y -= 1.0
                    y = float(int(y + 0.99))
                
                left_diff = abs(fixed_rect.left() - rect.left())
                right_diff = abs(fixed_rect.right() - rect.right())
                
                if right_diff > left_diff and left_diff <= magnet:
                    x = fixed_rect.left()
                elif right_diff <= magnet:
                    x = fixed_rect.right() - rect.width()

            return QRectF(x, y, rect.width(), rect.height())

        def rect_has_to_move_from(
                repulser_rect, rect,
                repulser_port_mode: int, rect_port_mode: int)->bool:
            left_spacing = right_spacing = box_spacing
            
            if (repulser_port_mode & PORT_MODE_INPUT
                    or rect_port_mode & PORT_MODE_OUTPUT):
                left_spacing = box_spacing_hor
            
            if (repulser_port_mode & PORT_MODE_OUTPUT
                    or rect_port_mode & PORT_MODE_INPUT):
                right_spacing = box_spacing_hor
            
            large_repulser_rect = repulser_rect.adjusted(
                - left_spacing, - box_spacing,
                right_spacing, box_spacing)

            return rect.intersects(large_repulser_rect)

        to_move_boxes = []
        repulsers = []
        wanted_directions = [wanted_direction]

        for box in repulser_boxes:
            srect = box.boundingRect()
            
            if new_scene_rect is not None:
                srect = new_scene_rect
            else:
                # if box is already moving, consider its end position
                for box_dict in self.move_boxes:
                    if box_dict['widget'] == box:
                        srect.translate(QPoint(box_dict['to_x'], box_dict['to_y']))
                        break
                else:
                    srect.translate(box.pos())

            repulser = {'rect': srect,
                        'item': box}
            repulsers.append(repulser)

            items_to_move = []

            for group in canvas.group_list:
                for widget in group.widgets:
                    if (widget is None
                            or widget in repulser_boxes
                            or widget in [b['item'] for b in to_move_boxes]
                            or widget in [b['widget'] for b in self.move_boxes]):
                        continue
                    
                    irect = widget.boundingRect()
                    irect.translate(widget.pos())

                    if rect_has_to_move_from(
                            repulser['rect'], irect,
                            repulser['item'].get_current_port_mode(),
                            widget.get_current_port_mode()):
                        items_to_move.append({'item': widget, 'rect': irect})
                    
            for box_dict in self.move_boxes:
                if (box_dict['widget'] in repulser_boxes
                        or box_dict['widget'] in [b['item'] for b in to_move_boxes]):
                    continue
            
                widget = box_dict['widget']
                irect = widget.boundingRect()
                irect.translate(QPoint(box_dict['to_x'], box_dict['to_y']))
                
                if rect_has_to_move_from(
                        repulser['rect'], irect,
                        repulser['item'].get_current_port_mode(),
                        widget.get_current_port_mode()):
                    items_to_move.append({'item': widget, 'rect': irect})
            
            for item_to_move in items_to_move:
                item = item_to_move['item']
                irect = item_to_move['rect']
                    
                # evaluate in which direction should go the box
                direction = get_direction(srect, irect, wanted_directions)
                to_move_box = {
                    'directions': [direction],
                    'pos': 0,
                    'item': item,
                    'repulser': repulser}
                
                # stock a position only for sorting reason
                if direction == DIRECTION_RIGHT:
                    to_move_box['pos'] = irect.left()
                elif direction == DIRECTION_LEFT:
                    to_move_box['pos'] = - irect.right()
                elif direction == DIRECTION_DOWN:
                    to_move_box['pos'] = irect.top()
                elif direction == DIRECTION_UP:
                    to_move_box['pos'] = - irect.bottom()

                to_move_boxes.append(to_move_box)

        # sort the list of dicts
        to_move_boxes = sorted(to_move_boxes, key = lambda d: d['pos'])
        to_move_boxes = sorted(to_move_boxes, key = lambda d: d['directions'])
        
        # the to_move_boxes list is dynamic
        # elements can be added to the list while iteration
        for to_move_box in to_move_boxes:
            item = to_move_box['item']
            repulser = to_move_box['repulser']
            ref_rect = repulser['rect']
            irect = item.boundingRect().translated(item.pos())

            directions = to_move_box['directions'].copy()
            new_direction = get_direction(repulser['rect'], irect, directions)
            directions.append(new_direction)
            
            # calculate the new position of the box repulsed by its repulser
            new_rect = repulse(new_direction, repulser['rect'], item,
                               repulser['item'].m_current_port_mode,
                               item.m_current_port_mode)
            
            active_repulsers = []
            
            # while there is a repulser rect at new box position
            # move the future box position
            while True:
                # list just here to prevent infinite loop
                # we save the repulsers that already have moved the rect
                for repulser in repulsers:
                    if rect_has_to_move_from(
                            repulser['rect'], new_rect,
                            repulser['item'].get_current_port_mode(),
                            item.get_current_port_mode()):

                        if repulser in active_repulsers:
                            continue
                        active_repulsers.append(repulser)
                        
                        new_direction = get_direction(
                            repulser['rect'], new_rect, directions)
                        new_rect = repulse(
                            new_direction, repulser['rect'], new_rect,
                            repulser['item'].m_current_port_mode,
                            item.m_current_port_mode)
                        directions.append(new_direction)
                        break
                else:
                    break

            # Now we know where the box will be definitely positioned
            # So, this is now a repulser for other boxes
            repulser = {'rect': new_rect, 'item': item}
            repulsers.append(repulser)
            
            # check which existing boxes exists at the new place of the box
            # and add them to this to_move_boxes iteration
            adding_list = []
            
            for group in canvas.group_list:
                for widget in group.widgets:
                    if (widget is None
                            or widget in repulser_boxes
                            or widget in [b['item'] for b in to_move_boxes]
                            or widget in [b['widget'] for b in self.move_boxes]):
                        continue
                    
                    mirect = widget.boundingRect().translated(widget.pos())
                    if rect_has_to_move_from(
                            new_rect, mirect,
                            to_move_box['item'].get_current_port_mode(),
                            widget.get_current_port_mode()):
                        adding_list.append(
                            {'directions': directions,
                            'pos': mirect.right(),
                            'item': widget,
                            'repulser': repulser})
            
            for box_dict in self.move_boxes:
                mitem = box_dict['widget']
                
                if (mitem in repulser_boxes
                        or mitem in [b['item'] for b in to_move_boxes]):
                    continue
                
                rect = mitem.boundingRect()
                rect.translate(QPoint(box_dict['to_x'], box_dict['to_y']))
                
                if rect_has_to_move_from(
                        new_rect, rect,
                        to_move_box['item'].get_current_port_mode(),
                        mitem.get_current_port_mode()):

                    adding_list.append(
                        {'directions': directions,
                         'pos': 0,
                         'item': box_dict['widget'],
                         'repulser': repulser})

            for to_move_box in adding_list:
                to_move_boxes.append(to_move_box)

            # now we decide where the box is moved
            pos_offset = item.boundingRect().topLeft()
            to_send_rect = new_rect.translated(- pos_offset)
            self.add_box_to_animation(
                item, to_send_rect.left(), to_send_rect.top())

    def bring_neighbors_and_deplace_boxes(self, box_widget, new_scene_rect):
        neighbors = [box_widget]
        limit_top = box_widget.pos().y()
        
        for neighbor in neighbors:
            srect = neighbor.boundingRect()
            for move_box in self.move_boxes:
                if move_box['widget'] == neighbor:
                    srect.translate(QPointF(move_box['to_x'], move_box['to_y']))
                    break
            else:
                srect.translate(neighbor.pos())

            for item in self.items(
                    srect.adjusted(
                        0, 0, 0,
                        canvas.theme.box_spacing + 1)):
                if item not in neighbors and item.type() == CanvasBoxType:
                    nrect = item.boundingRect().translated(item.pos())
                    if nrect.top() >= limit_top:
                        neighbors.append(item)
        
        neighbors.remove(box_widget)
        
        less_y = box_widget.boundingRect().height() - new_scene_rect.height()

        repulser_boxes = []

        for neighbor in neighbors:
            self.add_box_to_animation(
                neighbor, neighbor.pos().x(), neighbor.pos().y() - less_y)
            repulser_boxes.append(neighbor)
        repulser_boxes.append(box_widget)
        
        self.deplace_boxes_from_repulsers(repulser_boxes, wanted_direction=DIRECTION_UP)

    def center_view_on(self, widget):
        self.m_view.centerOn(widget)

    def removeItem(self, item):
        for child_item in item.childItems():
            QGraphicsScene.removeItem(self, child_item)
        QGraphicsScene.removeItem(self, item)

    def updateLimits(self):
        w0 = canvas.size_rect.width()
        h0 = canvas.size_rect.height()
        w1 = self.m_view.width()
        h1 = self.m_view.height()
        self.m_scale_min = w1/w0 if w0/h0 > w1/h1 else h1/h0

    def updateTheme(self):
        self.setBackgroundBrush(canvas.theme.canvas_bg)
        self.m_rubberband.setPen(canvas.theme.rubberband_pen)
        self.m_rubberband.setBrush(canvas.theme.rubberband_brush)

        cur_color = "black" if canvas.theme.canvas_bg.blackF() < 0.5 else "white"
        self.curCut = QCursor(QPixmap(":/cursors/cut-"+cur_color+".png"), 1, 1)
        self.curZoomArea = QCursor(QPixmap(":/cursors/zoom-area-"+cur_color+".png"), 8, 7)

    def get_new_scene_rect(self):
        first_pass = True

        for group in canvas.group_list:
            for widget in group.widgets:
                if widget is None or not widget.isVisible():
                    continue

                item_rect = widget.boundingRect().translated(widget.scenePos())
                item_rect = item_rect.marginsAdded(QMarginsF(50, 20, 50, 20))

                if first_pass:
                    full_rect = item_rect
                else:
                    full_rect = full_rect.united(item_rect)

                first_pass = False

        if not first_pass:
            return full_rect

        return QRectF()

    def resize_the_scene(self):
        if not options.elastic:
            return

        scene_rect = self.get_new_scene_rect()
        if not scene_rect.isNull():
            self.resizing_scene = True
            self.setSceneRect(scene_rect)
            self.resizing_scene = False

    def set_elastic(self, yesno: bool):
        options.elastic = True
        self.resize_the_scene()
        options.elastic = yesno

        if not yesno:
            # resize the scene to a null QRectF to auto set sceneRect
            # always growing with items
            self.setSceneRect(QRectF())

            # add a fake item with the current canvas scene size
            # (calculated with items), and remove it.
            fake_item = QGraphicsRectItem(self.get_new_scene_rect())
            self.addItem(fake_item)
            self.update()
            self.removeItem(fake_item)

    def set_prevent_overlap(self, yesno: bool):
        options.prevent_overlap = yesno

    def zoom_ratio(self, percent: float):
        ratio = percent / 100.0
        transform = self.m_view.transform()
        transform.reset()
        transform.scale(ratio, ratio)
        self.m_view.setTransform(transform)

        for group in canvas.group_list:
            for widget in group.widgets:
                if widget and widget.top_icon:
                    widget.top_icon.update_zoom(ratio)

    def zoom_fit(self):
        min_x = min_y = max_x = max_y = None
        first_value = True

        items_list = self.items()

        if len(items_list) > 0:
            for item in items_list:
                if item and item.isVisible() and item.type() == CanvasBoxType:
                    pos = item.scenePos()
                    rect = item.boundingRect()

                    x = pos.x() + rect.left()
                    y = pos.y() + rect.top()
                    if first_value:
                        first_value = False
                        min_x, min_y = x, y
                        max_x = x + rect.width()
                        max_y = y + rect.height()
                    else:
                        min_x = min(min_x, x)
                        min_y = min(min_y, y)
                        max_x = max(max_x, x + rect.width())
                        max_y = max(max_y, y + rect.height())

            if not first_value:
                self.m_view.fitInView(min_x, min_y, abs(max_x - min_x),
                                      abs(max_y - min_y), Qt.KeepAspectRatio)
                self.fixScaleFactor()

        if self.m_view:
            self.scaleChanged.emit(self.m_view.transform().m11())

    def zoom_in(self):
        view = self.m_view
        transform = view.transform()
        if transform.m11() < self.m_scale_max:
            transform.scale(1.2, 1.2)
            if transform.m11() > self.m_scale_max:
                transform.reset()
                transform.scale(self.m_scale_max, self.m_scale_max)
            view.setTransform(transform)
        self.scaleChanged.emit(transform.m11())

    def zoom_out(self):
        view = self.m_view
        transform = view.transform()
        if transform.m11() > self.m_scale_min:
            transform.scale(0.833333333333333, 0.833333333333333)
            if transform.m11() < self.m_scale_min:
                transform.reset()
                transform.scale(self.m_scale_min, self.m_scale_min)
            view.setTransform(transform)
        self.scaleChanged.emit(transform.m11())

    def zoom_reset(self):
        self.m_view.resetTransform()
        self.scaleChanged.emit(1.0)

    @pyqtSlot()
    def slot_selectionChanged(self):
        items_list = self.selectedItems()

        if len(items_list) == 0:
            self.pluginSelected.emit([])
            return

        plugin_list = []

        for item in items_list:
            if item and item.isVisible():
                group_item = None

                if item.type() == CanvasBoxType:
                    group_item = item
                elif item.type() == CanvasPortType:
                    group_item = item.parentItem()
                #elif item.type() in (CanvasLineType, CanvasBezierLineType, CanvasLineMovType, CanvasBezierLineMovType):
                    #plugin_list = []
                    #break

                if group_item is not None and group_item.m_plugin_id >= 0:
                    plugin_id = group_item.m_plugin_id
                    if plugin_id > MAX_PLUGIN_ID_ALLOWED:
                        plugin_id = 0
                    plugin_list.append(plugin_id)

        self.pluginSelected.emit(plugin_list)

    def triggerRubberbandScale(self):
        self.m_scale_area = True

        if self.curZoomArea:
            self.m_view.viewport().setCursor(self.curZoomArea)

    def send_zoom_to_zoom_widget(self):
        if not self.m_view:
            return
        canvas.qobject.zoom_changed.emit(self.m_view.transform().m11() * 100)

    def get_zoom_scale(self):
        return self.m_view.transform().m11()

    def keyPressEvent(self, event):
        if not self.m_view:
            event.ignore()
            return

        if event.key() == Qt.Key_Control:
            if self.m_mid_button_down:
                self.startConnectionCut()

        elif event.key() == Qt.Key_Home:
            event.accept()
            self.zoom_fit()
            return

        elif QApplication.keyboardModifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_Plus:
                event.accept()
                self.zoom_in()
                return

            if event.key() == Qt.Key_Minus:
                event.accept()
                self.zoom_out()
                return

            if event.key() == Qt.Key_1:
                event.accept()
                self.zoom_reset()
                return

        QGraphicsScene.keyPressEvent(self, event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            # Connection cut mode off
            if self.m_mid_button_down:
                self.m_view.viewport().unsetCursor()

        QGraphicsScene.keyReleaseEvent(self, event)

    def startConnectionCut(self):
        if self.curCut:
            self.m_view.viewport().setCursor(self.curCut)

    def zoom_wheel(self, delta):
        transform = self.m_view.transform()
        scale = transform.m11()

        if ((delta > 0 and scale < self.m_scale_max)
                or (delta < 0 and scale > self.m_scale_min)):
            # prevent too large unzoom
            if delta < 0:
                rect = self.sceneRect()

                top_left_vw = self.m_view.mapFromScene(rect.topLeft())
                bottom_right_vw = self.m_view.mapFromScene(rect.bottomRight())

                if (top_left_vw.x() > self.m_view.width() / 4
                        and top_left_vw.y() > self.m_view.height() / 4):
                    return

            # Apply scale
            factor = 1.4142135623730951 ** (delta / 240.0)
            transform.scale(factor, factor)
            self.fixScaleFactor(transform)
            self.m_view.setTransform(transform)
            self.scaleChanged.emit(transform.m11())

            # Update box icons especially when they are not scalable
            # eg. coming from theme
            for group in canvas.group_list:
                for widget in group.widgets:
                    if widget and widget.top_icon:
                        widget.top_icon.update_zoom(scale * factor)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            # parse items under mouse to prevent ACTION_DOUBLE_CLICK
            # if mouse is on a box
            items = self.items(
                event.scenePos(), Qt.ContainsItemShape, Qt.AscendingOrder)

            for item in items:
                if item.type() == CanvasBoxType:
                    break
            else:
                canvas.callback(ACTION_DOUBLE_CLICK, 0, 0, "")
                return

        QGraphicsScene.mouseDoubleClickEvent(self, event)

    def mousePressEvent(self, event):
        self.m_mouse_down_init = (
            (event.button() == Qt.LeftButton)
            or ((event.button() == Qt.RightButton)
                and QApplication.keyboardModifiers() & Qt.ControlModifier))
        self.m_mouse_rubberband = False

        if (event.button() == Qt.MidButton
                and QApplication.keyboardModifiers() & Qt.ControlModifier):
            self.m_mid_button_down = True
            self.startConnectionCut()

            pos = event.scenePos()
            self.m_pointer_border.moveTo(floor(pos.x()), floor(pos.y()))

            items = self.items(self.m_pointer_border)
            for item in items:
                if item and item.type() in (CanvasLineType, CanvasBezierLineType, CanvasPortType):
                    item.triggerDisconnect()

        QGraphicsScene.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        if self.m_mouse_down_init:
            self.m_mouse_down_init = False
            topmost = self.itemAt(event.scenePos(), self.m_view.transform())
            self.m_mouse_rubberband = not (
                topmost and topmost.type() in (CanvasBoxType,
                                               CanvasIconType,
                                               CanvasPortType,
                                               CanvasPortGroupType))
        if self.m_mouse_rubberband:
            event.accept()
            pos = event.scenePos()
            pos_x = pos.x()
            pos_y = pos.y()
            if not self.m_rubberband_selection:
                self.m_rubberband.show()
                self.m_rubberband_selection = True
                self.m_rubberband_orig_point = pos
            rubberband_orig_point = self.m_rubberband_orig_point

            x = min(pos_x, rubberband_orig_point.x())
            y = min(pos_y, rubberband_orig_point.y())

            lineHinting = canvas.theme.rubberband_pen.widthF() / 2
            self.m_rubberband.setRect(x+lineHinting,
                                      y+lineHinting,
                                      abs(pos_x - rubberband_orig_point.x()),
                                      abs(pos_y - rubberband_orig_point.y()))
            return

        if (self.m_mid_button_down
                and QApplication.keyboardModifiers() & Qt.ControlModifier):
            trail = QPolygonF([event.scenePos(), event.lastScenePos(), event.scenePos()])
            items = self.items(trail)
            for item in items:
                if item and item.type() in (CanvasLineType, CanvasBezierLineType):
                    item.triggerDisconnect()

        QGraphicsScene.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event):
        if self.m_scale_area and not self.m_rubberband_selection:
            self.m_scale_area = False
            self.m_view.viewport().unsetCursor()

        if self.m_rubberband_selection:
            if self.m_scale_area:
                self.m_scale_area = False
                self.m_view.viewport().unsetCursor()

                rect = self.m_rubberband.rect()
                self.m_view.fitInView(rect.x(), rect.y(), rect.width(), rect.height(), Qt.KeepAspectRatio)
                self.fixScaleFactor()

            else:
                items_list = self.items()
                for item in items_list:
                    if item and item.isVisible() and item.type() == CanvasBoxType:
                        item_rect = item.sceneBoundingRect()
                        item_top_left = QPointF(item_rect.x(), item_rect.y())
                        item_bottom_right = QPointF(item_rect.x() + item_rect.width(),
                                                    item_rect.y() + item_rect.height())

                        if self.m_rubberband.contains(item_top_left) and self.m_rubberband.contains(item_bottom_right):
                            item.setSelected(True)

            self.m_rubberband.hide()
            self.m_rubberband.setRect(0, 0, 0, 0)
            self.m_rubberband_selection = False

        else:
            items_list = self.selectedItems()
            for item in items_list:
                if item and item.isVisible() and item.type() == CanvasBoxType:
                    item.checkItemPos()
                    self.sceneGroupMoved.emit(item.getGroupId(), item.getSplittedMode(), item.scenePos())

            if len(items_list) > 1:
                self.update()

        self.m_mouse_down_init = False
        self.m_mouse_rubberband = False

        if event.button() == Qt.MidButton:
            event.accept()

            self.m_mid_button_down = False

            # Connection cut mode off
            if QApplication.keyboardModifiers() & Qt.ControlModifier:
                self.m_view.viewport().unsetCursor()
            return

        QGraphicsScene.mouseReleaseEvent(self, event)

    def wheelEvent(self, event):
        if not self.m_view:
            event.ignore()
            return

        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            event.accept()
            self.zoom_wheel(event.delta())
            return

        QGraphicsScene.wheelEvent(self, event)

    def contextMenuEvent(self, event):
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            event.accept()
            self.triggerRubberbandScale()
            return

        if len(self.selectedItems()) == 0:
            event.accept()
            x, y = event.screenPos().x(), event.screenPos().y()
            canvas.callback(ACTION_BG_RIGHT_CLICK, x, y, "")
            return

        QGraphicsScene.contextMenuEvent(self, event)

# ------------------------------------------------------------------------------------------------------------
