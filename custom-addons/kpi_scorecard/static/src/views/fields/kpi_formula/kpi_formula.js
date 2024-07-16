/** @odoo-module **/

import { loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
const { Component, onMounted, onPatched, onWillStart, onWillUpdateProps, useState } = owl;

const componentModel = "kpi.item";

jQuery.expr[":"].caseContains = function(a, i, m) {
    return jQuery(a).text().toUpperCase().indexOf(m[3].toUpperCase()) >= 0;
};

/*
* The method to caclulate the element all 4 corners positions
*/
function calculateCornersGrid(checkedJqueryObject) {
    const formulaContainerOffset = checkedJqueryObject.offset();
    return {
        "y1": formulaContainerOffset.top,
        "y2": formulaContainerOffset.top + checkedJqueryObject.outerHeight(),
        "x1": formulaContainerOffset.left,
        "x2": formulaContainerOffset.left + checkedJqueryObject.outerWidth(),
    };
};


export class KpiFormula extends Component {
    /*
    * Re-write to add services
    */
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({ 
            measures: [],
            constants: [],
            kpiIpds: [],
            operands: [],
            formulaParts: [],
        });
        this.targetObject = false;
        this.targetID = false;
        this.targetName = false;
        this.tempPart = false;
        onWillStart(async () => {
            const proms = [
                loadJS("/kpi_scorecard/static/lib/draggabilly/draggabilly.pkgd.min.js"),
                this._loadFormulaParts(this.props),
                this._loadFormulaMeasures(this.props),
            ]
            return Promise.all(proms);
        });
        onWillUpdateProps(async (nextProps) => {
            await this._loadFormulaParts(nextProps);
        });
        onMounted(() => {
            this.formulaContainer = $(".kpi-formula-content");
            this._activateDraggable($(".kpi-formula-element,.kpi-formula-part"));
        });
        onPatched(() => {
            this._activateDraggable($(".kpi-formula-element,.kpi-formula-part"));
            // restore previously hidden elements that are restored by the template rendering
            // IMPORTANT: owl does not allow deleting jquery elements updated by props
            $(".kpi-formula-element,.kpi-formula-part").removeClass("kpi-formula-hidden kpi-formula-no-impact");
        })
    }
    /*
    * The method to prepare the resulting Formula
    */
    async _loadFormulaParts(props) {       
        const formulaParts = await this.orm.call(
            componentModel,
            "action_render_formula",
            [props.value],
        );
        Object.assign(this.state, { formulaParts: formulaParts });
    }
    /*
    * The method to prepare dynamic fields to drag&drop
    */
    async _loadFormulaMeasures(props) {       
        const formulaMeasures = await this.orm.call(
            componentModel,
            "action_return_measures",
            [[props.record.data["id"]]],
        );
        Object.assign(this.state, { 
            measures: formulaMeasures.measures,
            constants: formulaMeasures.constants,
            kpiIpds: formulaMeasures.kpis,
            operands: formulaMeasures.operands,
        });
    }
    /*
     * The method to avoid dragging multiple objects and do not calc those for each move
    */ 
    _onDragStart(event, pointer) {
        if (!this.targetObject) {
            const currentTarget = event.currentTarget;
            this.targetObject = $(currentTarget);
            this.targetID = currentTarget.id;
            this.targetName = currentTarget.innerHTML;
            if (this.targetObject.hasClass("kpi-formula-number")) { this.targetName = currentTarget.id };
            const initalOffset = this.targetObject.offset();
            this.targetObject.attr("style", "position: absolute;");
            this.targetObject.addClass("kpi-formula-moving");
            this.targetObject.offset(initalOffset);
        };
    }
    /*
     * The method to show the current position of formula part
    */ 
    async _onDragMove(event, pointer, moveVector) {      
        $(".temp-kpi-formula-part").remove();
        const self = this;
        clearTimeout(this.dragMoveDebounceTimer);
        this.dragMoveDebounceTimer= setTimeout(async function() {
            const pageX = pointer.clientX;
            const pageY = pointer.clientY;
            if (self._checkContainerPosition(pageX, pageY)) {
                const neighbourData = await self._findClosestNeighbour(pageX, pageY);
                self._createFormulaPart(neighbourData.targetNeighbour, neighbourData.targetPosition);   
            }
        }, 100);
    }
    /*
     * The method to finalize drop
    */ 
    async _onDragEnd(event, pointer) {
        this.targetObject.attr("style", "");
        this.targetObject.removeClass("kpi-formula-moving");
        if (this.tempPart) {
            $(this.tempPart).removeClass("temp-kpi-formula-part");
        };
        if (!this.targetObject.hasClass("kpi-formula-element")) { 
            this.targetObject.addClass("kpi-formula-hidden kpi-formula-no-impact");
        };
        const formulaValue = await this._renderFormula();
        this.targetObject = false;
        this.targetID = false;
        this.targetName = false;
        this.targetDOM = false;
        if (this.tempPart) {
            $(this.tempPart).remove();
            this.tempPart = false;
        }
        this.props.update(formulaValue);
    }
    /*
     * The method to show variables full details
    */ 
    async _onStatiClick(event, pointer) {
        const actionDict = await this.orm.call(
            componentModel,
            "action_open_formula_part",
            [event.currentTarget.id],
        );
        if (actionDict) { this.actionService.doAction(actionDict) }; 
    }
    /*
     * The method to proceed search by variables
    */ 
    _onSearchNavigation(event, searchId) {
        const searchValue = event.currentTarget.value;
        if (searchId) {
            var formulaContainer = false;
            if (searchId == "MEASURE") { formulaContainer = $(".kpi-formula-container-measurements") } 
            else if (searchId == "KPI") { formulaContainer = $(".kpi-formula-container-other-kpi") } 
            else if (searchId == "CONST") { formulaContainer = $(".kpi-formula-container-constants") };
            if (formulaContainer) {
                const allVariables = formulaContainer.find(".kpi-formula-variable");
                if (searchValue) {
                    allVariables.addClass("kpi-formula-hidden");
                    formulaContainer.find(".kpi-formula-variable:caseContains("+ searchValue +")").removeClass("kpi-formula-hidden");
                } 
                else {
                    allVariables.removeClass("kpi-formula-hidden");
                }
            };
        };           
    }
    /*
     * The method to apply changes in number (before d&d to the formula)
    */ 
    _onChangeNumber(event) {
        const parentElement = $(event.target).closest("div")[0];
        parentElement.setAttribute("id", event.currentTarget.value);
    }
    /*
     * The method to activate draggable lib and assign event listeners
    */ 
    _activateDraggable(dragAndDropObject) {
        const self = this;
        const $draggable = dragAndDropObject.draggabilly({});
        $draggable.on("dragStart", function(event, pointer) { self._onDragStart(event, pointer) });
        $draggable.on("dragMove", function(event, pointer, moveVector) { self._onDragMove(event, pointer, moveVector) });
        $draggable.on("dragEnd", function(event, pointer) { self._onDragEnd(event, pointer) });
        $draggable.on("staticClick", function(event, pointer) { self._onStatiClick(event, pointer) });
    }
    /*
     * The method to render formula (string) based on final formula parts
    */ 
    async _renderFormula() {
        var finalFormula = $.Deferred();
        const allParts = $(".kpi-formula-part:not(.temp-kpi-formula-part):not(.kpi-formula-no-impact)");
        if (allParts.length == 0) { finalFormula.resolve("") }
        else {
            var tempFormula = "";
            _.each(allParts, function (formulaPart) {
                if (formulaPart && formulaPart.id) { tempFormula += formulaPart.id + ";" }; 
            }).promise().done(function() {
                finalFormula.resolve(tempFormula.slice(0, -1));
            });    
        }
        return finalFormula
    }
    /*
     * The method to check whether the mouse cursor is inside the formula container
    */ 
    _checkContainerPosition(pageX, pageY) {
        const formulaGrid = calculateCornersGrid(this.formulaContainer);
        if (pageX >= formulaGrid.x1 && pageX <= formulaGrid.x2 && pageY >= formulaGrid.y1 && pageY <= formulaGrid.y2) {
            return true;
        }
        return false;
    }   
    /*
     * The method to find the closest formula part neighbour
    */ 
    async _findClosestNeighbour(pageX, pageY) {
        var closestNeighbour = $.Deferred();
        const allPotentialParts = $(".kpi-formula-part:not(.temp-kpi-formula-part):not(.kpi-formula-moving)");
        if (allPotentialParts.length == 0) {
            closestNeighbour.resolve({
                "targetNeighbour": $(".kpi-formula-parts"),
                "targetPosition": "inside",
            });
        }
        else {
            var closestRowDifference = 10000,
                closestDifference = 10000,
                tempClosestNeighbour = false,
                checkedState = 0;
            _.each(allPotentialParts, function (formulaPart) {
                const partGrid = calculateCornersGrid($(formulaPart));
                const xDifference = (partGrid.x1 + partGrid.x2) / 2 - pageX;
                const yDifference = (partGrid.y1 + partGrid.y2) / 2 - pageY;
                const sqrDifference = Math.sqrt(xDifference * xDifference + yDifference * yDifference);
                const theSameRow = pageX >= partGrid.x1 && pageX <= partGrid.x2;
                const theSameColumn = pageY >= partGrid.y1 && pageY <= partGrid.y2;
                const neighbourCandidate = {
                    "targetNeighbour": $(formulaPart), 
                    "targetPosition": xDifference <= 0 ? "right" : "left",
                };
                if (theSameRow && theSameColumn) {
                    // there might be a single record that mouse can hover
                    tempClosestNeighbour = neighbourCandidate
                    checkedState = 3;
                }
                else if (checkedState < 3 && theSameRow) {
                    if (sqrDifference < closestRowDifference) {
                        tempClosestNeighbour = neighbourCandidate;
                        closestRowDifference = sqrDifference;
                    };
                    checkedState = 2;
                }
                else if (checkedState < 2) {
                    // if (checkedState < 2 && theSameColumn)
                    if (sqrDifference < closestDifference) {
                        tempClosestNeighbour = neighbourCandidate;
                        closestDifference = sqrDifference;
                    };
                    checkedState = 1;
                };
            }).promise().done(function() {
                if (tempClosestNeighbour) { closestNeighbour.resolve(tempClosestNeighbour) };
            });
        }
        return closestNeighbour;
    }
    /*
     * The method to prepare formula part based on the dragging info
    */ 
    _createFormulaPart(targetNeighbour, targetPosition) {
        if (
            this.targetID && this.targetName && targetPosition 
            && ( targetNeighbour.hasClass("kpi-formula-part") || targetNeighbour.hasClass("kpi-formula-parts") )
        ) {
            this.tempPart = document.createElement("div");
            this.tempPart.setAttribute("id", this.targetID);
            this.tempPart.innerHTML = this.targetName;
            $(this.tempPart).addClass("kpi-formula-part temp-kpi-formula-part");
            if (targetPosition == "left") { targetNeighbour.before(this.tempPart) }
            else if (targetPosition == "right") { targetNeighbour.after(this.tempPart) }
            else { $(this.tempPart).appendTo(targetNeighbour) };
        };
    }
};

KpiFormula.supportedTypes = ["char"];
KpiFormula.template = "kpi_scorecard.KpiFormula";
KpiFormula.props = { ...standardFieldProps };
registry.category("fields").add("kpi_formula", KpiFormula);
